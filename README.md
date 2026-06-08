# QueryToolbar Plugin for QGIS 4.0

Replicates the Manifold System Release 8.0 query toolbar with full enhancements (numeric spin boxes, date picker, NULL handling, unique values).

## How to install

1. Download the source code as a ZIP archive.
2. Uncompress the ZIP file.
3. Move the extracted `QueryToolbar` parent folder to the QGIS 4 plugins directory (create folders if they don't exist):  
   `%APPDATA%\QGIS\QGIS4\profiles\default\python\plugins`

> **Note:** Ensure you have a vector layer loaded in a QGIS 4.0 project before proceeding.

## How to use

1. Load a vector layer in QGIS 4.0.
2. Enable **QueryToolbar** from the **Plugin Manager**.
3. Pick a field, an operator, and a value (or NULL).
4. Click **Select** – matching features are highlighted immediately.
