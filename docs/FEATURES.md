# Adrenalin → Linux feature map

> "Experimental" means: FSR 4, FSR 3 via OptiScaler and Redstone frame generation rely on community Proton builds and DLL swaps, and may crash or misbehave in some games. Turn them off per game if they do, and never use OptiScaler in online games with anti-cheat.

What the Windows Radeon software does, and what Ember uses on Linux to do the same. Everything Ember builds on is open source. "Status" says how close the Linux result is.

## Performance tuning

| Adrenalin | Ember on Linux | Built on | Status |
|---|---|---|---|
| Tuning presets (Quiet / Balanced / Rage) | Profiles: Stock / Quiet / Balanced / Performance plus custom | amdgpu `pp_power_profile_mode`, `power1_cap` | Yes |
| Manual GPU tuning (max/min frequency) | Clocks & voltage | `pp_od_clk_voltage`: `s`/`m` per generation | needs `ppfeaturemask` overdrive bit (one click) |
| Voltage / undervolting | Voltage offset (RDNA 2–4), V/F curve point (RDNA 1/Vega 20), top-state voltage (Polaris/Vega 10) | `vo`, `vc`, `s N MHz mV` | undervolt only, by design |
| Power tuning (power limit) | Power limit slider | hwmon `power1_cap` | the board's VBIOS sets the range |
| Fan tuning / custom curve | Drag-and-drop curve, fixed speed, hysteresis, emergency override | `pwm1` loop (RDNA 1/2, GCN), firmware `gpu_od/fan_ctrl/fan_curve` (RDNA 3+) | Yes |
| Zero RPM, fan target temperature, acoustic limit | Fan firmware options | `fan_zero_rpm_enable`, `fan_target_temperature`, `acoustic_*_rpm_threshold`, `fan_minimum_pwm` | RDNA 3+ |
| Memory timing ("Fast Timing") | - | not exposed by amdgpu | No |
| Auto undervolt / auto overclock | - | needs a stress-test loop | Planned |
| Share tuning profiles (import / export) | Export to a file, import with every value re-checked against the importing card's limits | JSON profile files | Yes |
| Apply tuning at startup | Apply at boot + 90 s boot crash guard | systemd service | Yes |

## Gaming

| Adrenalin | Ember on Linux | Built on | Status |
|---|---|---|---|
| Per-game profiles | Automatic tuning-profile switch on game start/exit + per-game graphics | `/proc` watch for `SteamLaunch AppId=` and process names | Yes |
| **FSR 4 upgrade** (now on RX 6000 with the INT8 model) | FSR 4 toggle and indicator | `PROTON_FSR4_UPGRADE`, `PROTON_FSR4_INDICATOR` (Proton-GE, proton-cachyos ≥ 11.0-20260702 does it automatically) | experimental, RDNA 2/3/4: may break some games |
| FSR 3 / FSR 3 frame generation in any game | "FSR 3 in any game" + FSR 3 frame generation (replaces DLSS/XeSS inputs) | OptiScaler via `PROTON_USE_OPTISCALER` + `PROTON_OPTISCALER_CONFIG` (proton-cachyos ≥ 11.0-20260506, GE-Proton 11) | experimental: injection can break some games or anti-cheat; games with native FSR 3 work as-is |
| FSR Redstone (ML frame generation) | FSR frame generation toggle | `MLFG_UPGRADE` (+ `DXIL_SPIRV_CONFIG=wmma_rdna3_workaround` on RDNA 3) | experimental, custom Proton |
| Radeon Anti-Lag / Anti-Lag 2 | Anti-Lag | Mesa `VK_LAYER_MESA_anti_lag` (implements `VK_AMD_anti_lag`) | Vulkan / DXVK / VKD3D |
| Radeon Super Resolution (RSR) | Super Resolution for any game: 50–77% render scale | gamescope `-F fsr` / `nis` | Yes |
| Virtual Super Resolution (VSR) | Render at 150% / 200% and downscale | gamescope | Yes |
| Integer scaling | Integer scaling | gamescope `-S integer` | Yes |
| Radeon Image Sharpening | Image sharpening | vkBasalt FidelityFX CAS | Yes |
| Morphological AA | FXAA / SMAA | vkBasalt | Yes |
| Anisotropic filtering override | 4× / 8× / 16× | `RADV_TEX_ANISO` | Vulkan |
| Enhanced Sync / Wait for vertical refresh | VSync: App / On / Enhanced / Off | `MESA_VK_WSI_PRESENT_MODE` | Vulkan |
| Frame Rate Target Control / Radeon Chill ceiling | Frame rate target | MangoHud `fps_limit` | (fixed target, not Chill's dynamic range) |
| Performance overlay | Overlay: FPS / Standard / Detailed | MangoHud | Yes |
| HDR per game | HDR | Proton Wayland driver + `DXVK_HDR`, or gamescope `--hdr-enabled` | experimental |
| AFMF (driver frame generation for any game) | - | the closest open option is lsfg-vk, which needs the paid Lossless Scaling DLL | No no open equivalent yet |
| Radeon Boost (dynamic resolution) | - | no open implementation | No |
| "AMD Software active" in-game toast | "EMBER ACTIVE · game" banner with profile and features for the first seconds, then hidden | MangoHud `custom_text_center`, swapped out by rewriting its config in place (inotify reload) | games launched with `ember-run` |
| Game detection | Now Playing card, "Playing" badge, desktop notification | `SteamLaunch AppId=` in `/proc` | every Steam game, launch options not required |
| Add games from outside Steam | "Add game" picker of installed apps (Flatpak, Lutris, Heroic, Bottles, native) with icons, plus "Create launcher" | `.desktop` entries in the XDG data dirs; Flatpak `command=` from app metadata | Yes; launchers that hide the game process ask for it once |
| HYPR-RX one-click presets | Default / Quality / Performance / Power saver, global or per game | sets Anti-Lag, upscaling, sharpening, filtering and the FPS cap together | Yes |

## Display

| Adrenalin | Ember on Linux | Built on | Status |
|---|---|---|---|
| FreeSync | Off / Games / Always, plus the monitor's FreeSync range read from EDID | KDE `kscreen-doctor` VRR policy, EDID AMD VSDB | KDE Plasma |
| HDR, wide color gamut | toggles | kscreen-doctor | KDE |
| Color depth | Auto / 8 / 10 / 12 bpc | kscreen-doctor `maxbpc` | KDE |
| Pixel format / RGB range | Auto / Full / Limited | kscreen-doctor `rgbrange` | KDE |
| Refresh rate, resolution | chips | kscreen-doctor modes | KDE |
| Custom resolutions | - | kscreen-doctor `addCustomMode` | Planned |
| Brightness | DDC/CI brightness | kscreen-doctor | Yes |
| GNOME / Sway | - | compositor-specific | Planned contributions welcome |

## Record

| Adrenalin | Ember on Linux | Built on | Status |
|---|---|---|---|
| Record (start/stop) | Record page, tray, hotkey (Alt+F9) | gpu-screen-recorder with the GPU encoder (VA-API) | Yes |
| Instant Replay | Always-on buffer of 15 s to 10 min in RAM, save all or the last 15/30/60 s (Alt+F10), toggle with Alt+Shift+F10 | gpu-screen-recorder replay mode over its IPC socket | Yes |
| Record during Instant Replay | Recording starts inside the running replay session | `start-replay-recording` | Yes |
| Screenshot | Alt+F11 | gpu-screen-recorder | Yes |
| Hotkeys in fullscreen games | Registered with KDE's global shortcut service, rebindable in System Settings | KGlobalAccel | Yes on KDE; other desktops bind `ember --rec <action>` |
| Audio: desktop + microphone | Separate or mixed tracks | PipeWire/PulseAudio sources | Yes |
| Recording indicator in game | "REC", "Replay saved" messages | MangoHud config swap | Yes, for games launched with `ember-run` |
| Auto-start replay with games | Starts when a game is detected, stops when it closes | Ember game detection | Yes |
| Clips organized by game | `<Videos>/Ember/<Game>/<Game> <date> Replay.mp4` | | Yes |
| AV1 / HEVC / H.264 | Picks what the GPU's encoder supports | `gpu-screen-recorder --info` | AV1 needs RDNA 3+ |
| Live streaming | Twitch, YouTube or any RTMP server; H.264 at 3 to 12 Mbps with the GPU encoder | gpu-screen-recorder RTMP output (`-c flv`) | Yes |

## System & tools

| Adrenalin | Ember on Linux | Built on | Status |
|---|---|---|---|
| System info / issue report | System page + Copy report | sysfs, pci.ids, libdrm `amdgpu.ids`, vulkaninfo, glxinfo | Yes |
| Smart Access Memory indicator | ReBAR status | `mem_info_vis_vram_total == mem_info_vram_total` | Yes |
| Reset shader cache | Mesa cache + per-game Steam pre-caches | `~/.cache/mesa_shader_cache*`, `steamapps/shadercache` | Yes |
| Performance logging | Record to CSV | sysfs + `gpu_metrics` | Yes |
| Per-app GPU usage (Task Manager) | Apps using the GPU | DRM fdinfo (`drm-engine-*`, `drm-memory-vram`) | your own processes |
| Driver updates | - | Mesa ships with your distro | n/a on Linux |
| Noise suppression | - | see [Resona](https://github.com/noble6/resona) | - |

## Open-source projects Ember builds on or learned from

- **amdgpu** (Linux kernel) and **Mesa / RADV / radeonsi**: the driver itself
- **LACT** and **CoreCtrl**: the existing GPU control apps on Linux; their handling of quirks across GPU generations was a useful reference
- **amdgpu_top**: the fdinfo and `gpu_metrics` decoding approach
- **MangoHud**, **vkBasalt**, **gamescope**: the in-game layers Ember drives
- **Proton-GE**, **proton-cachyos**, **OptiScaler**: how FSR 4 reached RDNA 2 and 3 on Linux
- **KDE kscreen**: display configuration on Wayland
