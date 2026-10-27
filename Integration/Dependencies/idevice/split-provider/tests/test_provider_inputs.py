import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("provider_inputs", ROOT / "provider_inputs.py")
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


class ProviderContractTests(unittest.TestCase):
    def test_exact_contract_stays_disabled_and_has_all_reviewed_inputs(self):
        contract = provider.load_contract()
        self.assertFalse(contract["enabled"])
        self.assertFalse(contract["product_activation"])
        self.assertEqual(len(contract["entries"]), 443)
        self.assertEqual(sum(e["size"] for e in contract["entries"]), 40_506_667)
        self.assertEqual(set(contract["targets"]), set(provider.TARGETS))

    def test_each_target_has_explicit_library_choice(self):
        for target, data in provider.load_contract()["targets"].items():
            self.assertIn("OPENSSL_LIBS", data["environment_values"])
            self.assertEqual(data["environment_values"]["OPENSSL_LIBS"],
                             "ssl:crypto" if target.endswith("darwin") else "")
            self.assertEqual(data["environment_values"]["OPENSSL_NO_VENDOR"], "1")


class ProviderViewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.contract = copy.deepcopy(provider.load_contract())
        self.contract["entries"] = []
        files = {"LICENSE.txt": b"controlled license fixture\n"}
        for target, selected in self.contract["targets"].items():
            selected["header_count"] = 2
            files[selected["header_root"] + "/ssl.h"] = b"controlled header\n"
            files[selected["header_root"] + "/configuration.h"] = b"controlled configuration\n"
            for name in selected["native_library_input_paths"]:
                files[name] = b"controlled opaque archive fixture\n"
            if "framework_binary" in selected:
                files[selected["framework_binary"]] = b"controlled opaque framework fixture\n"
                files[selected["framework_root"] + "/Modules/module.modulemap"] = b"controlled module fixture\n"
        for name, data in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            mode = "100755" if name.endswith(".framework/OpenSSL") else "100644"
            path.chmod(0o755 if mode == "100755" else 0o644)
            self.contract["entries"].append({"path": name, "mode": mode, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()})
        patch = mock.patch.object(provider, "load_contract", return_value=self.contract)
        patch.start()
        self.addCleanup(patch.stop)

    def prepare(self, target="aarch64-apple-ios"):
        return provider.prepare_inputs(self.source, self.root / target, target)

    def test_apple_empty_libs_survive_environment_and_owned_dir_is_empty(self):
        receipt = self.prepare()
        env = provider.build_environment({"PATH": "/trusted/bin", "CARGO_HOME": "/owned/cargo"}, receipt)
        self.assertIn("AARCH64_APPLE_IOS_OPENSSL_LIBS", env)
        self.assertEqual(env["AARCH64_APPLE_IOS_OPENSSL_LIBS"], "")
        self.assertEqual(list((Path(receipt["view_root"]) / "lib").iterdir()), [])
        self.assertEqual(env["CARGO_HOME"], "/owned/cargo")
        self.assertEqual(receipt["final_link_arguments"][-2:], ["-framework", "OpenSSL"])

    def test_host_stages_only_two_selected_static_archives(self):
        receipt = self.prepare("aarch64-apple-darwin")
        env = provider.build_environment({}, receipt)
        self.assertEqual(env["AARCH64_APPLE_DARWIN_OPENSSL_LIBS"], "ssl:crypto")
        self.assertEqual({p.name for p in (Path(receipt["view_root"]) / "lib").iterdir()}, {"libssl.a", "libcrypto.a"})
        self.assertEqual(receipt["final_link_arguments"], [])

    def test_both_include_spellings_are_byte_identical(self):
        receipt = self.prepare("aarch64-apple-ios-sim")
        root = Path(receipt["view_root"])
        for name in ("ssl.h", "configuration.h"):
            self.assertEqual((root / "include/OpenSSL" / name).read_bytes(),
                             (root / "include/openssl" / name).read_bytes())
        self.assertTrue(provider.audit_inputs(receipt)["unchanged"])

    def test_discovery_and_compiler_overrides_removed_only_from_subprocess_copy(self):
        receipt = self.prepare()
        base = {k: "untrusted" for k in ("OPENSSL_DIR", "OPENSSL_CONF", "AARCH64_APPLE_DARWIN_OPENSSL_LIBS",
            "PKG_CONFIG_PATH", "TARGET_PKG_CONFIG_LIBDIR", "CC", "CC_aarch64_apple_ios", "HOST_CFLAGS",
            "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_TARGET_AARCH64_APPLE_IOS_LINKER", "SDKROOT", "CPATH",
            "CARGO_BUILD_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_TARGET")}
        base["PATH"] = "/trusted/bin"
        original = dict(base)
        env = provider.build_environment(base, receipt)
        self.assertEqual(base, original)
        self.assertEqual({k: v for k, v in env.items() if k not in receipt["environment"]}, {"PATH": "/trusted/bin"})

    def test_wrong_target_is_rejected_before_output(self):
        with self.assertRaises(provider.InputError):
            self.prepare("x86_64-unknown-linux-gnu")
        self.assertFalse((self.root / "x86_64-unknown-linux-gnu").exists())

    def test_missing_input_leaves_no_view(self):
        (self.source / "LICENSE.txt").unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assertFalse((self.root / "aarch64-apple-ios").exists())

    def test_equal_size_changed_input_is_rejected(self):
        p = self.source / "LICENSE.txt"
        p.write_bytes(b"x" * p.stat().st_size)
        with self.assertRaises(provider.InputError):
            self.prepare()

    def test_input_executable_mode_mismatch_is_rejected(self):
        (self.source / "LICENSE.txt").chmod(0o755)
        with self.assertRaises(provider.InputError):
            self.prepare()

    def test_input_symlink_is_rejected(self):
        p = self.source / "LICENSE.txt"
        p.rename(self.source / "original")
        p.symlink_to("original")
        with self.assertRaises(provider.InputError):
            self.prepare()

    def test_existing_output_is_not_overwritten(self):
        self.prepare()
        with self.assertRaises(provider.InputError):
            self.prepare()

    def test_output_under_source_is_rejected_without_mutation(self):
        before = sorted(str(p.relative_to(self.source)) for p in self.source.rglob("*"))
        with self.assertRaises(provider.InputError):
            provider.prepare_inputs(self.source, self.source / "new-view", "aarch64-apple-ios")
        self.assertEqual(before, sorted(str(p.relative_to(self.source)) for p in self.source.rglob("*")))

    def test_parent_alias_cannot_redirect_output_under_source(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(provider.InputError):
            provider.prepare_inputs(self.source, alias / "new-view", "aarch64-apple-ios")
        self.assertFalse((self.source / "new-view").exists())

    def test_receipt_metadata_changes_are_rejected(self):
        receipt = self.prepare()
        for key, value in (("schema", 2), ("source_commit", "0" * 40), ("verified_input_count", 0),
                           ("verified_input_bytes", 0), ("header_count", 0), ("include_spellings", ["OpenSSL"])):
            changed = copy.deepcopy(receipt)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(provider.InputError):
                provider.audit_inputs(changed)

    def test_apple_view_rejects_added_archive(self):
        receipt = self.prepare()
        (Path(receipt["view_root"]) / "lib/libssl.a").write_bytes(b"unexpected")
        with self.assertRaises(provider.InputError):
            provider.build_environment({}, receipt)

    def test_owned_header_mutation_is_rejected(self):
        receipt = self.prepare()
        (Path(receipt["view_root"]) / "include/openssl/ssl.h").write_bytes(b"changed")
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def test_source_framework_cannot_gain_an_umbrella_header(self):
        receipt = self.prepare()
        selected = self.contract["targets"][receipt["target"]]
        (self.source / selected["header_root"] / "extra.h").write_bytes(b"unexpected")
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def test_source_framework_cannot_gain_an_unlisted_module(self):
        receipt = self.prepare()
        selected = self.contract["targets"][receipt["target"]]
        (self.source / selected["framework_root"] / "Modules/extra.modulemap").write_bytes(b"unexpected")
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def test_include_root_cannot_shadow_sdk_headers(self):
        receipt = self.prepare()
        (Path(receipt["view_root"]) / "include/stdint.h").write_bytes(b"shadow")
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def test_view_root_symlink_is_rejected(self):
        receipt = self.prepare()
        root = Path(receipt["view_root"])
        moved = root.with_name("moved")
        root.rename(moved)
        root.symlink_to(moved)
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def test_source_root_symlink_is_rejected(self):
        receipt = self.prepare()
        moved = self.source.with_name("moved-source")
        self.source.rename(moved)
        self.source.symlink_to(moved)
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def test_empty_libs_cannot_be_omitted_or_changed_in_receipt(self):
        for value in (None, "ssl:crypto"):
            with self.subTest(value=value):
                receipt = self.prepare("aarch64-apple-ios" if value is None else "aarch64-apple-ios-sim")
                key = receipt["target"].upper().replace("-", "_") + "_OPENSSL_LIBS"
                if value is None:
                    del receipt["environment"][key]
                else:
                    receipt["environment"][key] = value
                with self.assertRaises(provider.InputError):
                    provider.build_environment({}, receipt)

    def test_framework_path_substitution_is_rejected(self):
        receipt = self.prepare()
        receipt["final_link_arguments"][1] = "/other/provider"
        with self.assertRaises(provider.InputError):
            provider.audit_inputs(receipt)

    def output(self, receipt, libs):
        root = receipt["view_root"]
        return (f"cargo:rustc-link-search=native={root}/lib\ncargo:include={root}/include\n"
                + "cargo:version_number=30600020\n"
                + "".join(f"cargo:rustc-link-lib={lib}\n" for lib in libs)).encode()

    def test_expected_apple_and_host_build_directives(self):
        for target, libs in (("aarch64-apple-ios", []), ("aarch64-apple-darwin", ["static=ssl", "static=crypto"])):
            receipt = self.prepare(target)
            result = provider.check_build_script_output(self.output(receipt, libs), receipt)
            self.assertEqual(result["link_libraries"], libs)

    def test_apple_static_or_framework_emission_is_rejected(self):
        receipt = self.prepare()
        for libs in (["static=ssl"], ["framework=OpenSSL"], ["dylib=crypto"]):
            with self.subTest(libs=libs), self.assertRaises(provider.InputError):
                provider.check_build_script_output(self.output(receipt, libs), receipt)

    def test_double_colon_directives_are_checked_identically(self):
        receipt = self.prepare()
        output = self.output(receipt, []).replace(b"cargo:", b"cargo::")
        self.assertEqual(provider.check_build_script_output(output, receipt)["link_libraries"], [])
        with self.assertRaises(provider.InputError):
            provider.check_build_script_output(output + b"cargo::rustc-link-lib=static=ssl\n", receipt)

    def test_link_args_flags_and_env_directives_are_rejected(self):
        receipt = self.prepare()
        for directive in (b"rustc-link-arg=-lcrypto", b"rustc-link-arg-tests=-lcrypto", b"rustc-flags=-lssl",
                          b"rustc-env=RUSTFLAGS=-lssl"):
            for prefix in (b"cargo:", b"cargo::"):
                with self.subTest(directive=directive, prefix=prefix), self.assertRaises(provider.InputError):
                    provider.check_build_script_output(self.output(receipt, []) + prefix + directive + b"\n", receipt)

    def test_modern_metadata_cannot_override_expected_legacy_values(self):
        receipt = self.prepare()
        for directive in (b"awslc=true", b"include=/other", b"version_number=1"):
            with self.subTest(directive=directive), self.assertRaises(provider.InputError):
                provider.check_build_script_output(self.output(receipt, []) + b"cargo::metadata=" + directive + b"\n", receipt)

    def test_build_output_reaudits_receipt(self):
        receipt = self.prepare()
        output = self.output(receipt, [])
        receipt["environment"]["AARCH64_APPLE_IOS_OPENSSL_LIBS"] = "ssl:crypto"
        with self.assertRaises(provider.InputError):
            provider.check_build_script_output(output, receipt)

    def test_wrong_header_version_search_or_provider_branch_rejected(self):
        receipt = self.prepare()
        output = self.output(receipt, [])
        for bad in (output.replace(b"30600020", b"30500010"),
                    output.replace(b"native=", b"framework="), output + b"cargo:boringssl=true\n",
                    output + b"cargo:rustc-cfg=awslc\n"):
            with self.assertRaises(provider.InputError):
                provider.check_build_script_output(bad, receipt)

    def test_build_output_size_is_bounded(self):
        receipt = self.prepare()
        with self.assertRaises(provider.InputError):
            provider.check_build_script_output(b"x" * (1024 * 1024 + 1), receipt)


if __name__ == "__main__":
    unittest.main()
