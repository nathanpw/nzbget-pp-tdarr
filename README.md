# nzbget-pp-tdarr

A post process plugin for NZBGet which will move one or more files to a directory for processing by Tdarr. It connects to the Tdarr API to ensure the file gets picked up and processed (by Tdarr). This plugin is not fault tolerant of Tdarr failures. Once complete in Tdarr it will move the file back for nzbget to mark as successful.

The plugin will process multiple files if downloaded together in one NZB.

Setting the NZBGet PostStrategy (in Settings -> DOWNLOAD QUEUE) to Aggressive or higher is recommended if you want to be able to continue to download files while tdarr is processing files.

The plugin assumes your files will be extracted and cleaned up prior to be processed by nzbget-pp-tdarr. Ideally only the files to be scanned/processed should be left in the root directory. Duplicate file names could cause issues.
