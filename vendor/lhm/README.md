# Bundled third-party libraries

These DLLs are loaded at runtime (via pythonnet) to read CPU and motherboard
temperatures on Windows. They are redistributed here so the packaged app works
without a separate install. See `src/temperature_monitor.py`.

| File | Source | Version | License |
|------|--------|---------|---------|
| `LibreHardwareMonitorLib.dll` | [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) | 0.9.3 (net472) | MPL-2.0 |
| `HidSharp.dll` | [HidSharp](https://www.nuget.org/packages/HidSharp) | 2.1.0 (net35) | Apache-2.0 / MIT |

## Why 0.9.3 specifically

Newer LibreHardwareMonitorLib (0.9.4+) pulls heavier .NET Framework
dependencies (`System.Memory`, etc.) that are **not** in the .NET Framework GAC,
so `Computer.Open()` fails with `FileNotFoundException: System.Memory`. The
0.9.3 net472 build's only real dependency is `System.Management`, which **is** a
GAC assembly on .NET Framework — so just these two DLLs are sufficient.

`System.Management` is provided by the OS; do not add it here.

## Updating

Download the matching versions from NuGet and copy the `lib/net472`
(LibreHardwareMonitorLib) and `lib/net35` (HidSharp) builds. pythonnet has no
app.config, so binding redirects do not apply — bundle the exact versions the
LHM build references.
