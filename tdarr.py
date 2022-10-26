#!/usr/bin/env python3
#
##############################################################################
### NZBGET POST-PROCESSING SCRIPT                                          ###

# Convert Video files using tdarr.
#
# This script converts video files from the download directory using tdarr.
#
# NOTE: This script requires Python to be installed on your system.
# Linux only!

##############################################################################
### OPTIONS                                                                ###

# Tdarr Domain
#
# This is the domain to used to query the tdarr API. (i.e.: localhost:8265)
#tdarrDomain=localhost:8265

# Tdarr Process Directory
#
# Directory where files are temporarily moved for processing by Tdarr.
# Supports using the $DestDir variable (only).
#tdarrProcessDirectory=$DestDir/tdarr/process

# Wait Period
#
# The period in seconds to wait between tdarr API queries. (i.e.: 60 seconds)
#waitPeriod=60

# Periods To Wait for Tdarr
#
# The maximum amount of periods to wait for tdarr to pick up the file.
#periodsToWaitforTdarr=5

# Extensions To Check
#
# Comma seperated list of extensions to check files are queued by tdarr.
#extensionsToCheck=mkv,mp4,mov,m4v,mpg,mpeg,avi,flv,webm,wmv,vob,evo,iso,m2ts,ts

### NZBGET POST-PROCESSING SCRIPT                                          ###
##############################################################################

import os
import sys
import json
import requests
import sched
import concurrent.futures
import time
from pprint import pprint # for printing Python dictionaries in a human-readable way

# Should be false, except when debugging/testing outside nzbget.
skipNZBChecks=False

# NZBGet V11+
# Check if the script is called from nzbget 11.0 or later
if skipNZBChecks or 'NZBOP_SCRIPTDIR' in os.environ and not os.environ['NZBOP_VERSION'][0:5] < '11.0':
    # Exit codes used by NZBGet
    POSTPROCESS_PARCHECK=92
    POSTPROCESS_SUCCESS=93
    POSTPROCESS_ERROR=94
    POSTPROCESS_NONE=95
    # Allow debugging mode when skipNZBChecks is true.
    if skipNZBChecks:
        print ("[INFO] Script triggered from outisde NZBGet.")
        # Define variables for testing outside of nzbget.
        processDirectory="/path/sonarr/test"
        tdarrDomain="localhost:8265"
        tdarrProcessDirectory="/path/tdarr/process"
        waitPeriod=60
        periodsToWaitforTdarr=5
        extensionsToCheck="mkv,mp4,mov,m4v,mpg,mpeg,avi,flv,webm,wmv,vob,evo,iso,m2ts,ts"
        print ("[INFO] Post-Process: Option variables set.")
        # Replacement variables for tdarr nodes (node:server)
        pathTranslators={
            "/path/node" : "/path/server"
        }
    else:
        print ("[INFO] Script triggered from NZBGet (11.0 or later).")
        # Check if destination directory exists (important for reprocessing of history items)
        if not os.path.isdir(os.environ['NZBPP_DIRECTORY']):
            print ("[ERROR] Post-Process: Nothing to post-process: destination directory ", os.environ['NZBPP_DIRECTORY'], "doesn't exist")
            sys.exit(POSTPROCESS_ERROR)
        processDirectory=os.environ['NZBPP_DIRECTORY']
        # Set the option variables.
        tdarrDomain = os.environ['NZBPO_TDARRDOMAIN']
        tdarrProcessDirectory = os.environ['NZBPO_TDARRPROCESSDIRECTORY']
        waitPeriod = os.environ['NZBPO_WAITPERIOD']
        waitPeriod = int(waitPeriod)
        periodsToWaitforTdarr = os.environ['NZBPO_PERIODSTOWAITFORTDARR']
        periodsToWaitforTdarr = int(periodsToWaitforTdarr)
        extensionsToCheck = os.environ['NZBPO_EXTENSIONSTOCHECK']
        # Replace $DestDir in tdarr process directory
        DestDir=os.environ['NZBOP_DESTDIR']
        tdarrProcessDirectory = tdarrProcessDirectory.replace("$DestDir", DestDir)
        print ("[INFO] Post-Process: Option variables set.")

    # Make sure the extensions to check starts with a period.
    extensionsToProcess = []
    for ext in extensionsToCheck.split(','):
        if ext.startswith('.'):
            extensionsToProcess.append(ext)
        else:
            extensionsToProcess.append("."+ext)

    # Helper function to Setup file data required for processing.
    def emptyFiletoProcess(file):
        fileToProcess = {}
        fileToProcess['nzbgetFile'] = file
        fileToProcess['tdarrFile'] = ""
        fileToProcess['convertedFile'] = ""
        fileToProcess['waits'] = 0
        fileToProcess['tdarrData'] = ""
        fileToProcess['failed'] = False
        return fileToProcess

    # Helper function to get file path, name, and extension
    def getFilePathinfo(file):
        filePath = os.path.dirname(file)
        fileName = os.path.basename(file)
        fileName, fileExtension = os.path.splitext(fileName)
        return filePath, fileName, fileExtension

    # Function for processing threaded files
    def fileThread(file):
        print ("[INFO] Thread started for processing file: ", file)
        fileToProcess = filesToProcess[file]
        # Move files for tdarr processing.
        filePath, fileName, fileExtension = getFilePathinfo(fileToProcess['nzbgetFile'])
        filesToProcess[file]['tdarrFile'] = os.path.join(tdarrProcessDirectory, fileName, fileName) + fileExtension
        print ("[INFO] Making directory for Tdarr processing: ", os.path.dirname(fileToProcess['tdarrFile']))
        os.mkdir(os.path.dirname(fileToProcess['tdarrFile']))
        print ("[INFO] Moving ",fileToProcess['nzbgetFile']," to ", fileToProcess['tdarrFile'])
        os.rename(fileToProcess['nzbgetFile'], fileToProcess['tdarrFile'])
        s = sched.scheduler(time.time, time.sleep)
        s.enter(waitPeriod, 1, checkTdarr, (s,file,fileToProcess))
        s.run()
        # TODO: Add some post processing checking to see if they succeeded and get the new/original file name from tdarr.
        # TODO: Add some ability to retry in tdarr (with a parameterized option)?

    # Function to check tdarr for individual files.
    def checkTdarr(sc, file, fileToProcess):
        # Transform the paths for tdarr if debugging/testing.
        if skipNZBChecks :
            for node, server in pathTranslators.items():
                fileToProcess['tdarrFile'] = fileToProcess['tdarrFile'].replace(node,server)
        headers = {"content-type": "application/json"}
        payload = {"data": {
            "string": "_id,"+fileToProcess['tdarrFile'],
            "lessThanGB": 9999,
            "greaterThanGB": 0
            }}
        tdarrURL = "http://"+tdarrDomain+"/api/v2/search-db"
        response = requests.post(tdarrURL, json=payload, headers=headers)
        # Increment the amount of waits.
        fileToProcess['waits'] += 1
        print ("[INFO] Post-Process: Tdarr API Attempt: ", fileToProcess['waits']," for file : ", file)
        if response.ok:
            respObjects = json.loads(response.text)
            numObjects = len(respObjects)
            print ("[INFO] Post-Process: Tdarr returned ", numObjects," objects", file)
            if (numObjects > 1):
                print ("[ERROR] Post-Process: Found ", len(respObjects), " tdarr entries for ", file)
                fileToProcess['failed'] = True
                sys.exit(0)
            elif  (numObjects < 0):
                print ("[ERROR] Post-Process: Couldn't find ", fileToProcess['tdarrFile'], " in tdarr after ", fileToProcess['waits'], "waiting periods.")
                fileToProcess['failed'] = True
                sys.exit(0)
            elif (numObjects == 0 and fileToProcess['waits'] < periodsToWaitforTdarr):
                print ("[INFO] Post-Process: Waiting for tdarr to pick up : ", file)
                sc.enter(waitPeriod, 1, checkTdarr, (sc, file, fileToProcess))
            for object in respObjects:
                # Possible outputs from Tdarr states/queues are:
                #  'TranscodeDecisionMaker': 'Transcode success',
                #  'TranscodeDecisionMaker': 'Transcode error',
                #  'TranscodeDecisionMaker': 'Not required',
                #  'TranscodeDecisionMaker': 'Queued',
                print ("[INFO] Post-Process: Tdarr returned TranscodeDecisionMaker = ", object['TranscodeDecisionMaker'])
                if (object['TranscodeDecisionMaker'] == "Queued"):
                    print ("[INFO] Post-Process: Waiting for tdarr to complete processing file : ", file)
                    sc.enter(waitPeriod, 1, checkTdarr, (sc, file, fileToProcess))
                else:
                    fileToProcess['tdarrData'] = object
        else:
            print ("[ERROR] Post-Process: tdarr API returned a ", response.status_code," error.")
            fileToProcess['failed'] = True
            sys.exit(0)

    # Get all the files we will need to process.
    filesToProcess = {}
    print ("[INFO] Post-Process: Walking directory:",processDirectory)
    for dirpath, dirnames, filenames in os.walk(processDirectory):
        for file in filenames:
            print ("[INFO] Post-Process: Checking file:", file)
            filePath, fileName, fileExtension = getFilePathinfo(file)
            fullFilePath=os.path.join(dirpath, file)
            if fileExtension in extensionsToProcess:
                filesToProcess[fullFilePath] = emptyFiletoProcess(fullFilePath)
                print ("[INFO] Post-Process: Found ",fullFilePath," to be processed.")
    print ("[INFO] Post-Process: found ", len(filesToProcess)," files to process.")

    # Start a thread for processing each file.
    # for file, fileToProcess in filesToProcess.items():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_url = {executor.submit(fileThread, elem): elem for elem in filesToProcess}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                future.result()
            except Exception as exc:
                print('[ERROR] '.format(exc))

    # Tdarr processing is done, lets check the results and move files back to nzbget.
    for file, fileToProcess in filesToProcess.items():
        # Possible outputs from Tdarr states/queues are:
        #  'TranscodeDecisionMaker': 'Transcode success',
        #  'TranscodeDecisionMaker': 'Transcode error',
        #  'TranscodeDecisionMaker': 'Not required',
        #  'TranscodeDecisionMaker': 'Queued',
        if fileToProcess['tdarrData']['TranscodeDecisionMaker'] == "Transcode success":
            # Use the filename/_id returned by tdarr, in case the extension changes.
            fileToProcess['tdarrFile'] = fileToProcess['tdarrData']['_id']

        # Transform the paths for tdarr if debugging/testing.
        if skipNZBChecks :
            for node, server in pathTranslators.items():
                fileToProcess['tdarrFile'] = fileToProcess['tdarrFile'].replace(server,node)

        # Move the files back and clean up.
        print ("[INFO] Moving ",fileToProcess['tdarrFile']," to ",fileToProcess['nzbgetFile'])
        os.rename(fileToProcess['tdarrFile'], fileToProcess['nzbgetFile'])
        dateFile=os.path.join(os.path.dirname(fileToProcess['tdarrFile']),fileName) + ".dates"
        if os.path.exists(dateFile):
            os.remove(dateFile)
        os.rmdir(os.path.dirname(fileToProcess['tdarrFile']))

    sys.exit(POSTPROCESS_SUCCESS)
