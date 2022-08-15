# from imp import load_compiled
from re import A
from tkinter import N
import boto3
import logging
import sys
import argparse
import time


logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)

# Create the parser
my_parser = argparse.ArgumentParser(description='Upfate addon script for EKS')

# Add the arguments
my_parser.add_argument("-p",
                       "--profile",
                       metavar='profile',
                       type=str,
                       default='DEV-admin-access',
                       help='the profile name using for authentication')
my_parser.add_argument("-r",
                       "--region",
                       metavar='region',
                       type=str,
                       default='us-east-1',
                       help='the EKS region which should be updated')
my_parser.add_argument("cluster",
                       metavar='cluster',
                       type=str,
                       help='the EKS cluster which should be updated')
my_parser.add_argument("-u",
                       action='store_true',
                       help='a boolean property which requres update')
args = my_parser.parse_args()

logging.info("Going to update %s cluster on %s regtion with %s profile (update = %s)", args.cluster, args.region, args.profile, args.u)

addOnsNotToUpdate = []                             #list of add-ons that shouldn't be updated
timeToWaitWhenUpdating = 120                                 #how much time to wait when udating an add-on
timeToCheckUpdateStatus = 5                                  #how much time to wait to check the status of the update


def getLatestRelevantVerions(addOnVersions, clusterVersion):
    versionNum = 0
    compatibilitiesListNum = 0

    # Get the last version availalbe for current cluster version
    # lastAddonV = getLatestRelevantVerions() -> new function
    while versionNum <  len(addOnVersions['addons'][0]['addonVersions']):
        while compatibilitiesListNum < len(addOnVersions['addons'][0]['addonVersions'][versionNum]['compatibilities']):
            addOnClusterVersion = addOnVersions['addons'][0]['addonVersions'][versionNum]['compatibilities'][compatibilitiesListNum]['clusterVersion']
            if addOnClusterVersion == clusterVersion:
                lastAddonV = addOnVersions['addons'][0]['addonVersions'][versionNum]['addonVersion']
                return(lastAddonV)
            compatibilitiesListNum += 1
        versionNum += 1

def checkHTTPStatusCode(ResponseMetadata):
    #checks responsse status and if theres an error quits the program
    if 200 != ResponseMetadata['ResponseMetadata']['HTTPStatusCode']:
        logging.info("An error has accured with HTTP Status Code")
        sys.exit(1)

def updateAddOn(addOn, lastAddonVersion, roleArnOfServiceAccount):
    #updates the add-on
    logging.info("Going to update addon: " + addOn)
    if roleArnOfServiceAccount == None:
        responseU = client.update_addon(
        clusterName = args.cluster,
        addonName = addOn,
        addonVersion = lastAddonVersion,
        resolveConflicts='OVERWRITE'
        )
    else:
        responseU = client.update_addon(
            clusterName = args.cluster,
            addonName = addOn,
            addonVersion = lastAddonVersion,
            serviceAccountRoleArn = roleArnOfServiceAccount,
            resolveConflicts='OVERWRITE'
        )
    checkHTTPStatusCode(responseU)
    checkUpdate(addOn, responseU['update']['id'])

def checkUpdate(addOn, idOfUpdate):
    #checks the status of the update
    global timeToWaitWhenUpdating
    global timeToCheckUpdateStatus
    while timeToWaitWhenUpdating > 0:
        responseDU = client.describe_update(
            name = args.cluster,
            updateId = idOfUpdate,
            addonName = addOn
        )
        checkHTTPStatusCode(responseDU)
        logging.info("Update status: " + responseDU['update']['status'])
        if responseDU['update']['status'] != 'InProgress':
            if responseDU['update']['status'] == 'Failed':
                logging.info("The update failed.")
                sys.exit(2)
            elif responseDU['update']['status'] == 'Cancelled':
                logging.info("The update was cancelled")
                sys.exit(3)
            else:
                logging.info("The add-on is udated.")
                return()

        timeToWaitWhenUpdating -= timeToCheckUpdateStatus
        time.sleep(timeToCheckUpdateStatus)
    logging.info("It takes too much time to update this add-on.")
    sys.exit(4)
        


update = args.u
profile_name = args.profile
region_name = args.region
clusterName = args.cluster

session = boto3.Session(profile_name = args.profile,
                        region_name = args.region)
client = session.client('eks')

response = client.describe_cluster(
    name = args.cluster
)
checkHTTPStatusCode(response)

clusterVersion = response['cluster']['version']

response = client.list_addons(
    clusterName = args.cluster,
    maxResults=100
)
checkHTTPStatusCode(response)

addOns = response['addons']
stopUpdating = False

# Iterate over all addons, and try to upgrade each addon if upgrade available 
for addOn in addOns:
    response = client.describe_addon_versions(
        maxResults=100,
        addonName= addOn
    )
    checkHTTPStatusCode(response)
    

    responseC = client.describe_addon(
        clusterName = args.cluster,
        addonName=addOn
    )
    checkHTTPStatusCode(responseC)

    lastAddonV = getLatestRelevantVerions(response, clusterVersion)
    currentAddonV = responseC['addon']['addonVersion']
    if lastAddonV == currentAddonV:
        logging.info("Add-on name: %s, there are no updates for this add-on. (Version: %s )", addOn, currentAddonV, )
    else: # Update available
        notUpdateAddonNum = 0
        updateAddon = True
        logging.info("Add-on name: %s, there is a new version available for this add-on: version: %s . (current version: %s )", addOn, lastAddonV, currentAddonV)
        
        # skip addons which don't require update or update is not possible
        while notUpdateAddonNum < len(addOnsNotToUpdate) and update == True:
            if addOn == addOnsNotToUpdate[notUpdateAddonNum]:
                logging.info("Not udating add-on: "+ addOn)
                updateAddon = False
            notUpdateAddonNum += 1
        
        key = 'serviceAccountRoleArn'
        if key in responseC['addon']:
            roleArnOfServiceAccount =  responseC['addon']['serviceAccountRoleArn']
        else:
            roleArnOfServiceAccount = None
        print(roleArnOfServiceAccount)
        if update == True and updateAddon == True:
            updateAddOn(addOn, lastAddonV, roleArnOfServiceAccount)