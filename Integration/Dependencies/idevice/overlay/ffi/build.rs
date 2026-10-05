// Jackson Coxson

use std::{env, fs::OpenOptions, io::Write};

const HEADER: &str = r#"// Jackson Coxson
// Bindings to idevice - https://github.com/jkcoxson/idevice

#ifdef _WIN32
  #ifndef WIN32_LEAN_AND_MEAN
  #define WIN32_LEAN_AND_MEAN
  #endif
  #include <winsock2.h>
  #include <ws2tcpip.h>
  typedef int                idevice_socklen_t;
  typedef struct sockaddr    idevice_sockaddr;
#else
  #include <sys/types.h>
  #include <sys/socket.h>
  typedef socklen_t          idevice_socklen_t;
  typedef struct sockaddr    idevice_sockaddr;
#endif
"#;

fn main() {
    let crate_dir = env::var("CARGO_MANIFEST_DIR").unwrap();

    let builder = cbindgen::Builder::new()
        .with_crate(crate_dir)
        .with_header(HEADER)
        .with_language(cbindgen::Language::C)
        .with_include_guard("IDEVICE_H")
        .exclude_item("idevice_socklen_t")
        .exclude_item("idevice_sockaddr");

    // Retain the unmodified generator output for the narrow two-type comparison.
    // The Apple recipe verifies both outputs before compiling any consumer probe.
    builder.clone().generate()
        .expect("Unable to generate baseline bindings")
        .write_to_file("idevice.cbindgen-baseline.h");
    let bindings = builder
        .exclude_item("TetherlessPairingValidationResult")
        .exclude_item("TetherlessPairingHostResult")
        .with_after_include(include_str!("pairing_result_abi.h"))
        .generate()
        .expect("Unable to generate bindings");
    bindings.write_to_file("idevice.cbindgen-scoped.h");
    bindings.write_to_file("idevice.h");

    // Check if plist.h exists locally first, otherwise download
    let plist_h_path = "plist.h";
    let h = if std::path::Path::new(plist_h_path).exists() {
        std::fs::read_to_string(plist_h_path).expect("failed to read plist.h")
    } else {
        panic!("plist.h missing");
    };

    let mut f = OpenOptions::new().append(true).open("idevice.h").unwrap();
    f.write_all(b"\n\n\n").unwrap();
    f.write_all(&h.into_bytes())
        .expect("failed to append plist.h");

    let f = std::fs::read_to_string("idevice.h").unwrap();
    std::fs::write("../cpp/include/idevice.h", f).unwrap();
}
