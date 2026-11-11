# Custom Edition unsigned build

HaloPad 0.3.15 still builds Custom Edition 1.10. An Xbox-only IPA is not a substitute: it has no translated `data/modules` and the edition picker reports Custom Edition as not included. This checkout does not contain the installer, product key, or game files, and no IPA was compiled here.

## Two layouts

| | Older personal IPA | Current builder / PadMint |
| --- | --- | --- |
| Translated shell | `Payload/HaloPad.app/data/modules` | `Payload/HaloPad.app/data/modules` plus `data/core-identity.json` |
| Stock files | `Payload/HaloPad.app/bundled-game` (`haloce.exe`, maps, DLLs, shaders, and the rest of that tree) | Not inside the IPA. Sidecar `<ipa>.data/Halo-CE.halopad.zip`, imported after install |
| Executable | The app binary. `haloce.exe` is data | The app binary. `haloce.exe` inside the zip is data |

`data/modules` from an older IPA belong to that translation. They are not a drop-in for a newly built 0.3.15 shell. A key-installed `haloce.exe` can also differ from the engineering profile in `config/profiles/custom-en-1.0.10.0621.json`; see `docs/INPUTS.md`. The app accepts stock only when every file matches the signed inventory.

## Noninteractive Mac route

This is the route that produces the translated shell. It runs only on an Apple silicon Mac and only with files you already own. Do not put the installer or the product key on a command line that is logged, and do not upload either file.

Prerequisites, all local:

- Xcode 26 or later, opened once
- `brew install sevenzip winetricks llvm lld cmake ninja sdl3`
- Wine from `docs/INSTALL-WINE.md`
- A directory containing `HaloCESetup.exe` whose SHA-256 is the installer recorded in `padmint.json`, and `product-key.txt` (one line, the key). The 1.10 update may sit beside them; otherwise the builder downloads Bungie's free patch and checks its recorded hash.

The builder reads the key from the file, not from an argument:

```sh
scripts/builder/build.sh /private/path/to/installer-folder \
  --xbox \
  --app-version 0.3.15 \
  --app-build 1 \
  --out /private/halopad-build \
  --ipa /private/halopad-build/HaloPad.ipa
```

`--xbox` keeps the OpenCE edition in the same app. Omit it only for a Custom Edition shell with no Xbox engine. Stdin is not a TTY in this command, so a missing `product-key.txt` stops the build instead of prompting. The unsigned IPA and `HaloPad.ipa.data/Halo-CE.halopad.zip` are personal files. Do not commit, upload, or publish them.

After a normal install, choose the zip inside HaloPad. That remains the compatible import for a shell that was not repacked.

## Private `bundled-game` repack

Use this only after the Mac route has produced an unsigned `HaloPad.app` with `data/modules` and `data/core-identity.json`. Point `--game` at your own stock directory (the old IPA's `bundled-game`, or the folder the builder assembled). The script copies inventory matches, skips everything else, and does not print hashes or key material.

```sh
python3 scripts/repack-prebundled-game.py \
  --app /private/halopad-build/HaloPad.app \
  --game /private/path/to/stock \
  --ipa /private/halopad-build/HaloPad-prebundled.ipa
```

The app you pass is not modified. On success the new unsigned IPA contains `Payload/HaloPad.app/bundled-game` plus the original `data/modules`. A Mac shell uses `Contents/Resources/bundled-game`. At launch, a bundled tree that matches the signed inventory is used offline. A mismatch leaves the prepared-package and folder import in place.

Paths inside the git checkout are accepted only when git already ignores them (`generated/` is ignored). Do not point the script at a tracked directory.

If the stock bytes do not match `core-identity.json`, the script stops. The prerequisite is then a stock tree produced for this shell (the builder's assembled files or a prepared package you already imported), not the raw older IPA by itself.

## Signing

Signing identity `dev.halopad.HaloPad.robby` is applied by Devices. This repository does not sign, install, or merge. The base bundle id stays `dev.halopad.HaloPad`. `CFBundleShortVersionString` and `CFBundleVersion` are left as built (`0.3.15` / the build number you passed). The device profile must include that device and both of these entitlements, which the shell already requests:

- `com.apple.developer.kernel.extended-virtual-addressing`
- `com.apple.developer.kernel.increased-memory-limit`

## Installed-stock regeneration

The old personal IPA's `haloce.exe`, `Keystone.dll`, `ksimeui.dll`, and `controls/Controls.dll` match `config/profiles/custom-en-1.0.10.0621.json`. That installed tree can regenerate the current translation. The builder checks those hashes and does not copy `data/modules` or `data/image.bin`.

`--installed-stock` does not read a product key and refuses `--xbox-only`. Halo still reads `HKLM\Software\Microsoft\Microsoft Games\Halo CE\PID` and `DigitalProductID` at startup. Those values are not in the executable or the maps. Pass the file the player's own app already has. If it is missing, stop: a new ID still needs `PidGen.dll` from `HaloCESetup.exe` and the product key.

MSXML 4 is not in `bundled-game`. Pass `data/reference` from the same app. The pinned redistributable hashes are checked, and a different file is refused.

```sh
export DEVELOPER_DIR=/Applications/Xcode_26.6.app/Contents/Developer
scripts/builder/build.sh \
  --installed-stock /private/old-ipa/Payload/HaloPad.app/bundled-game \
  --reference-root /private/old-ipa/Payload/HaloPad.app/data/reference \
  --product-id-file /private/old-ipa/Payload/HaloPad.app/data/config/runtime/product-id.txt \
  --xbox \
  --app-version 0.3.15 \
  --app-build 1 \
  --out /private/halopad-build \
  --ipa "$OUTPUT_IPA"
```

`$OUTPUT_IPA` is the unsigned combined IPA. It contains the new `data/modules` and `Payload/HaloPad.app/bundled-game`, so the first launch does not ask for an import. `$OUTPUT_IPA.data/Halo-CE.halopad.zip` is also written. Bundle id stays `dev.halopad.HaloPad`.

Prebuild on the hosted runner. Wine is not required for this path:

```sh
brew install llvm lld cmake ninja sdl3
```

Script-mode inputs. Do not change `rokoben-a11y/ios-signing`. Resign stays off.

```text
repo_url: https://github.com/rokoben-a11y/projectreach.git
ref: cursor/ce-prebundle-duo-controls-54b5
build_script: scripts/builder/build.sh --installed-stock "$HALOPAD_STOCK" --reference-root "$HALOPAD_REFERENCE" --product-id-file "$HALOPAD_PRODUCT_ID" --xbox --app-version 0.3.15 --app-build 1 --ipa "$OUTPUT_IPA"
prebuild: brew install llvm lld cmake ninja sdl3
xcode: /Applications/Xcode_26.6.app
resign: off
```

## What is still required

- The three private paths above, taken from the old IPA and not committed
- An Apple silicon Mac with Xcode 26.6 and the prebuild tools, to actually translate and compile
- Devices signing with the existing identity and both memory entitlements
- No IPA was compiled in this Linux pass
