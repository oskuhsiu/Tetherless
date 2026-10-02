#!/usr/bin/env python3
"""Add an isolated XCUITest target to a prepared project. Product sources unchanged."""
from pathlib import Path
import hashlib
import shutil
import sys
import xml.etree.ElementTree as ET

APP = 'BFD247692284B9A500981D42'
PROJECT = 'BFD247622284B9A500981D42'
TARGET = 'F10000000000000000000004'
EXPECTED = 'a511c447bd71311bffb6d116a3cb0025a75561d4'

def once(text, old, new):
    if text.count(old) != 1: raise ValueError('UI project anchor changed: ' + old[:40])
    return text.replace(old, new, 1)

def patch_project(text):
    if TARGET in text: raise ValueError('UI target already present')
    additions = {
        'PBXBuildFile': 'F10000000000000000000001 = {isa = PBXBuildFile; fileRef = F10000000000000000000002; };',
        'PBXFileReference': '''F10000000000000000000002 = {isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = TetherlessUITests.swift; sourceTree = "<group>"; };
F10000000000000000000003 = {isa = PBXFileReference; explicitFileType = wrapper.cfbundle; path = TetherlessUITests.xctest; sourceTree = BUILT_PRODUCTS_DIR; };''',
        'PBXGroup': 'F10000000000000000000005 = {isa = PBXGroup; children = (F10000000000000000000002,); path = TetherlessUITests; sourceTree = "<group>"; };',
        'PBXSourcesBuildPhase': 'F10000000000000000000006 = {isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = (F10000000000000000000001,); runOnlyForDeploymentPostprocessing = 0; };',
        'PBXFrameworksBuildPhase': 'F10000000000000000000007 = {isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0; };',
        'PBXResourcesBuildPhase': 'F10000000000000000000008 = {isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0; };',
        'PBXContainerItemProxy': f'F10000000000000000000009 = {{isa = PBXContainerItemProxy; containerPortal = {PROJECT}; proxyType = 1; remoteGlobalIDString = {APP}; remoteInfo = SideStore; }};',
        'PBXTargetDependency': f'F1000000000000000000000A = {{isa = PBXTargetDependency; target = {APP}; targetProxy = F10000000000000000000009; }};',
        'PBXNativeTarget': f'''{TARGET} = {{isa = PBXNativeTarget; buildConfigurationList = F1000000000000000000000B;
buildPhases = (F10000000000000000000006,F10000000000000000000007,F10000000000000000000008,);
buildRules = (); dependencies = (F1000000000000000000000A,); name = TetherlessUITests;
productName = TetherlessUITests; productReference = F10000000000000000000003;
productType = "com.apple.product-type.bundle.ui-testing"; }};''',
        'XCConfigurationList': 'F1000000000000000000000B = {isa = XCConfigurationList; buildConfigurations = (F1000000000000000000000C,F1000000000000000000000D,); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release; };',
    }
    settings = '''CLANG_ENABLE_MODULES = YES; GENERATE_INFOPLIST_FILE = YES; IPHONEOS_DEPLOYMENT_TARGET = 17.0;
PRODUCT_BUNDLE_IDENTIFIER = org.tetherless.TetherlessUITests; PRODUCT_NAME = "$(TARGET_NAME)";
SWIFT_VERSION = 5.0; SDKROOT = iphoneos; TARGETED_DEVICE_FAMILY = "1,2"; TEST_TARGET_NAME = SideStore;
LD_RUNPATH_SEARCH_PATHS = ("$(inherited)", "@executable_path/Frameworks", "@loader_path/Frameworks",);'''
    additions['XCBuildConfiguration'] = '\n'.join(
        f'{ident} = {{isa = XCBuildConfiguration; buildSettings = {{{settings}}}; name = {name}; }};'
        for ident, name in [('F1000000000000000000000C','Debug'),('F1000000000000000000000D','Release')])
    for section, contents in additions.items():
        marker = f'/* End {section} section */'
        text = once(text, marker, contents + '\n' + marker)
    text = once(text, 'BFD247612284B9A500981D42 = {\n\t\t\tisa = PBXGroup;\n\t\t\tchildren = (',
                'BFD247612284B9A500981D42 = {\n\t\t\tisa = PBXGroup;\n\t\t\tchildren = (\n\t\t\t\tF10000000000000000000005,')
    text = once(text, '\t\t\ttargets = (', '\t\t\ttargets = (\n\t\t\t\t' + TARGET + ',')
    return text

def scheme():
    root = ET.Element('Scheme', LastUpgradeVersion='2630', version='1.7')
    build = ET.SubElement(root, 'BuildAction', parallelizeBuildables='YES', buildImplicitDependencies='YES')
    entries = ET.SubElement(build, 'BuildActionEntries')
    for identifier,name,product in [(APP,'SideStore','SideStore.app'),(TARGET,'TetherlessUITests','TetherlessUITests.xctest')]:
        entry = ET.SubElement(entries,'BuildActionEntry',buildForTesting='YES',buildForRunning='NO',buildForProfiling='NO',buildForArchiving='NO',buildForAnalyzing='YES')
        ET.SubElement(entry,'BuildableReference',BuildableIdentifier='primary',BlueprintIdentifier=identifier,
                      BuildableName=product,BlueprintName=name,ReferencedContainer='container:AltStore.xcodeproj')
    action = ET.SubElement(root,'TestAction',buildConfiguration='Debug',selectedDebuggerIdentifier='Xcode.DebuggerFoundation.Debugger.LLDB',
                           selectedLauncherIdentifier='Xcode.IDEFoundation.Launcher.PosixSpawn',shouldUseLaunchSchemeArgsEnv='NO')
    refs = ET.SubElement(action,'Testables')
    ref = ET.SubElement(refs,'TestableReference',skipped='NO',parallelizable='NO')
    ET.SubElement(ref,'BuildableReference',BuildableIdentifier='primary',BlueprintIdentifier=TARGET,
                  BuildableName='TetherlessUITests.xctest',BlueprintName='TetherlessUITests',ReferencedContainer='container:AltStore.xcodeproj')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def apply(root):
    project = root/'AltStore.xcodeproj/project.pbxproj'
    raw = project.read_bytes()
    if hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() != EXPECTED:
        raise ValueError('Unreviewed prepared UI-test project')
    patched = patch_project(raw.decode())
    output = root/'TetherlessUITests'
    if output.exists(): raise ValueError('UI test output already exists')
    shutil.copytree(Path(__file__).with_name('UITests'), output)
    project.write_text(patched)
    (project.parent/'xcshareddata/xcschemes/TetherlessUITests.xcscheme').write_bytes(scheme())

if __name__ == '__main__': apply(Path(sys.argv[1]))
