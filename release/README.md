# Paste bundles

For machines where files cannot be downloaded: open a bundle's **Raw** view, select all, copy, paste into a new file
with the same name, save as UTF-8, and run `python <file>`. It recreates the `nifi-kb` folder next to it and checks
every file's hash (a cut-off or damaged paste is reported, not written).

- `nifi-kb-0.5.0-bundle.py` - everything in one file (868 KB)
- `parts/` - the same in 5 parts of about 200 KB, for clipboard / editor limits; unpack each into the same folder

Regenerate after changes: `python ops/bundle.py --out release` and `python ops/bundle.py --max-kb 200 --out release/parts`.
