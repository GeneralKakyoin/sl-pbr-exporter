# Second Life Creator Suite - Workspace Guidelines

## Mandatory Addon Sync & Deployment
Whenever source files in `src/sl_pbr_exporter/` or `blender_manifest.toml` are added, modified, or deleted:

1. **Rebuild & Deploy Automatically**:
   Immediately run the deployment script after modifying code:
   ```powershell
   python scripts/deploy_to_blender.py
   ```
   This script builds both distribution packages in `dist/` and syncs the updated files directly to:
   * **Blender 3.6**: `%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons\sl_pbr_exporter`
   * **Blender 5.2**: `%APPDATA%\Blender Foundation\Blender\5.2\extensions\user_default\sl_pbr_exporter`

2. **Notify User to Reload**:
   Always remind the user to reload the scripts in their active Blender session:
   * Press `F3` -> `Reload Scripts` (`bpy.ops.script.reload()`), OR
   * Restart Blender if UI/operator classes were fundamentally re-registered.

3. **Verify Tests**:
   Ensure headless tests pass before finishing:
   ```powershell
   & "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" --background --python tests/run_tests.py
   ```
