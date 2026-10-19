load("@build_bazel_rules_apple//apple:apple.bzl", "apple_dynamic_framework_import")

apple_dynamic_framework_import(
    name = "Python",
    framework_imports = glob(["vendor/Python.xcframework/ios-arm64/Python.framework/**"]),
    visibility = ["//visibility:public"],
)

objc_library(
    name = "ExteraPlugins",
    module_name = "ExteraPlugins",
    enable_modules = True,
    srcs = ["EPPluginHost.m", "EPPluginManagerController.m"],
    hdrs = ["EPPluginHost.h", "EPPluginManagerController.h"],
    sdk_frameworks = ["Foundation", "UIKit", "AVFoundation", "UniformTypeIdentifiers"],
    deps = [":Python"],
    visibility = ["//visibility:public"],
)
