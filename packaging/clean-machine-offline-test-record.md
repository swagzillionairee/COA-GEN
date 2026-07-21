# Clean-machine offline packaging test record

Release candidate: `0.3.0`  
Status: **NOT YET EXECUTED — release blocker**  
Tester: ____________________  
Date: ____________________  
VM image / snapshot: ____________________

This record must be completed against the actual SHA-256-identified setup
executable on a clean x64 Windows VM with networking disabled. Packaging source
or a successful Linux test run is not evidence that the installer passed.

| Check | Windows 10 22H2 | Windows 11 23H2/24H2 | Notes / evidence |
| --- | --- | --- | --- |
| Standard-user per-user install; no admin prompt | ☐ | ☐ | |
| Start Menu shortcut and optional desktop shortcut | ☐ | ☐ | |
| Browser opens only on `127.0.0.1` | ☐ | ☐ | |
| Preferred-port conflict selects another loopback port | ☐ | ☐ | |
| Double launch reuses healthy instance | ☐ | ☐ | |
| Exit action stops all packaged processes | ☐ | ☐ | |
| Relaunch after browser close creates no duplicate/orphan | ☐ | ☐ | |
| Paths with spaces and non-ASCII characters | ☐ | ☐ | |
| PDF, JSON, CSV/ZIP batch and images work offline | ☐ | ☐ | |
| Standard and AES-256 protected PDF verification | ☐ | ☐ | |
| Fonts/templates/frontend load with network disabled | ☐ | ☐ | |
| No writes occur under the installation directory | ☐ | ☐ | |
| Settings/numbering survive in-place upgrade | ☐ | ☐ | |
| Uninstall removes program and shortcuts | ☐ | ☐ | |
| Uninstall preserves user reports/scenarios/local state | ☐ | ☐ | |
| Antivirus and code-signature checks recorded | ☐ | ☐ | |

Installer filename: ____________________  
SHA-256: ____________________  
Adobe Acrobat Pro version and permission result: ____________________  
Independent viewer/editor and result: ____________________  
Exceptions / release approval: ____________________
