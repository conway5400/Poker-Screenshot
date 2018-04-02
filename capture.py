import sys, os
import time
import threading
import cv2
import boto3
import httplib2

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from pprint import pprint


timeStr = ""
screenCaptureFilepath = ""
prevCurrentHandNum = ""

DIMENSIONS = {
    "CURRENT_HAND_NUMBER" : ((655, 655+266), (157, 157+50)),
    "LAST_HAND_NUMBER" : ((597, 597+266), (225, 225+50)),
}

PLAYER_BALANCE_WIDTH = 440
PLAYER_BALANCE_HEIGHT = 200

NINE_PLAYER_DIMENSIONS_BALANCES = {
    "PLAYER_1" : ((1351, 1351 + PLAYER_BALANCE_WIDTH), (310, 310 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_2" : ((2109, 2109 + PLAYER_BALANCE_WIDTH), (310, 310 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_3" : ((2807, 2807 + PLAYER_BALANCE_WIDTH), (581, 581 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_4" : ((2863, 2863 + PLAYER_BALANCE_WIDTH), (1156, 1156 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_5" : ((2354, 2354 + PLAYER_BALANCE_WIDTH), (1638, 1638 + PLAYER_BALANCE_HEIGHT - 50)),
    "PLAYER_6" : ((1640, 1640 + PLAYER_BALANCE_WIDTH), (1680, 1680 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_7" : ((1048, 1048 + PLAYER_BALANCE_WIDTH), (1635, 1635 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_8" : ((574, 574 + PLAYER_BALANCE_WIDTH), (1141, 1141 + PLAYER_BALANCE_HEIGHT)),
    "PLAYER_9" : ((634, 634 + PLAYER_BALANCE_WIDTH), (600, 600 + PLAYER_BALANCE_HEIGHT - 50)),
}


def main():
    global prevCurrentHandNum

    time.sleep(2)
    print "Running Poker Screenshot function....."

    # if current hand number is not equal to last stored current hand number, we update it
    currentHandNum = getCurrentHandNum()

    if(currentHandNum != prevCurrentHandNum):
        print "*" * 50
        print "NEW HAND!"
        print "Last Saved Hand #: " + prevCurrentHandNum
        print "Current Hand #: " + currentHandNum
        print "*" * 50

        prevCurrentHandNum = currentHandNum
        newPlayerBalances = getAllPlayerBalances()
        newPlayerBalances.insert(0,currentHandNum)
        addToSpreadsheet(newPlayerBalances)

    else:
        print "*" * 50
        print "Hand # has not changed since last check!"
        print "*" * 50        

    #run function again and keep on checking
    # main()

def getAllPlayerBalances():
    global screenCaptureFilepath
    global timeStr

    playerBalances = []

    for x in range(1, 10):
        player = "PLAYER_" + str(x)

        playerBalanceImage = scaleImage(getCroppedImage(cv2.imread(screenCaptureFilepath), NINE_PLAYER_DIMENSIONS_BALANCES[player]), 2)
        newFileName = timeStr + "-player" + str(x) + ".png"
        newFilePath = "/Users/conwaysolomon/Documents/CodingDojo/Poker/images/" + newFileName
        saveNewImage(newFilePath, playerBalanceImage) 

        playerCurrentBalText = getTextFromImage(newFileName, newFilePath)
        playerCurrentBalText = playerCurrentBalText.replace(',', '')

        playerBalances.append(playerCurrentBalText)

        print "Player #" + str(x) + " Balance: " + playerCurrentBalText

    return playerBalances

#function to get current hand number as text
def getCurrentHandNum():
    global timeStr
    global screenCaptureFilepath

    #in order to get the current hand number, must first capture the screen
    #first we get new screen capture file path and current time string
    #returns the timeStr of request and file path of full screen capture
    (timeStr, screenCaptureFilepath) = getScreenshot()

    #assuming photos is in correct format, we crop just the current hand number piece
    (currentHandFileName, currentHandFilePath) = findCurrentHand(timeStr, screenCaptureFilepath)
    
    #get text version of image from current hand file photo through aws upload to S3 and rekognition
    currentHandNumText = getTextFromImage(currentHandFileName, currentHandFilePath)

    return currentHandNumText

# get screenshot of screen currently and return the timestring it 
# was taken and full file path of the screenshot
def getScreenshot():
    print("Getting screenshot....")

    #saving new screenshot as current date/time
    timeval = time.gmtime()
    timestr = time.strftime("%Y%m%d-%H%M%S")

    #saving new screenshot as current date/time
    filePath = "/Users/conwaysolomon/Documents/CodingDojo/Poker/screencaptures/" + timestr + ".png"
    command = "screencapture " + filePath
    os.system(command)

    #return filepath of new screenshot
    return (timestr, filePath)


#function takes in a filepath and timestring of image and returns the file name and path of the current hand number
def findCurrentHand(timeStr, filePath):  
    currentHandNumImage = scaleImage(getCroppedImage(cv2.imread(filePath), DIMENSIONS["CURRENT_HAND_NUMBER"]), 4)
    newFileName = timeStr + "-currenthand.png"
    newFilePath = "/Users/conwaysolomon/Documents/CodingDojo/Poker/images/" + newFileName
    saveNewImage(newFilePath, currentHandNumImage)
    return (newFileName, newFilePath)

# function takes in a filepath and timestring of image and returns the file name and path of the last hand number
def findLastHand(timeStr, filePath):
    lastHandNumImage = scaleImage(getCroppedImage(image, DIMENSIONS["LAST_HAND_NUMBER"]), 4)
    newFileName = timeStr + "-lasthand.png"
    newFilePath = "/Users/conwaysolomon/Documents/CodingDojo/Poker/images/" + newFileName
    saveNewImage(newFilePath, lastHandNumImage)
    return newFilePath

#given a cv2 image and a filepath, saves/writes new image
def saveNewImage(filePath, image):
    
    cv2.imwrite(filePath, image)

#given an image name and assuming uploaded to s3 bucket, returns the text from the image
def getTextFromImage(imageName, filePath):

    #upload image of current hand crop to S3 bucket
    uploadToS3(imageName, filePath)

    #set S3 bucket name to poker and key to the given file name
    bucket = "conway-poker"
    key = imageName

    #run through rekognition
    rekognition = boto3.client("rekognition", "us-east-2")
    response = rekognition.detect_text(
        Image={
            "S3Object": {
                "Bucket": bucket,
                "Name": key,
            }
        }
    )

    #parse the response
    detections = response['TextDetections']

    #go through detections and return the first (for now) WORD type
    # this ignores LINE types
    foundTextArr = []
    foundText = ""
    for detection in detections: 
        type = detection['Type']
        # id = int(detection['Id'])

        if type == "WORD":
            foundText +=  detection['DetectedText']
    
    return foundText


#given a file path and file name, this uploads to the S3 poker bucket
def uploadToS3(fileName, filePath):
    s3 = boto3.resource('s3')
    data = open(filePath, 'rb')
    s3.Bucket('conway-poker').put_object(Key=fileName, Body=data)

#given an image and set of coordinates in tuple format, return the crop of that image
def getCroppedImage(image, dim):
    x1 = dim[0][0] 
    x2 = dim[0][1]
    y1 = dim[1][0]
    y2 = dim[1][1]

    newImage = image[y1:y2, x1:x2]
    return newImage

# given an image and scale by factor (- or +, scales and returns the image by that factor)
def scaleImage(image, scaleBy):
    (h, w) = image.shape[:2]

    if scaleBy > 0:
        dim = (w * scaleBy, h * scaleBy)
    else:
        scaleBy = abs(scaleBy)
        dim = (w / scaleBy, h / scaleBy)

    resized = cv2.resize(image, dim, interpolation = cv2.INTER_AREA)
    return resized

def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'sheets.googleapis.com-python-quickstart.json')

    store = Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        if flags:
            credentials = tools.run_flow(flow, store, flags)
        else: # Needed only for compatibility with Python 2.6
            credentials = tools.run(flow, store)
        print('Storing credentials to ' + credential_path)
    return credentials

def addToSpreadsheet(valuesArr):
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('sheets', 'v4', credentials=credentials)

    spreadsheet_id = '19JcCdcMmAiqZz2z3NnodwEYzJRhTkPP6nwetcXS6exg'
    range_ = '9Players!A1:J100'
    value_input_option = 'USER_ENTERED'
    insert_data_option = 'INSERT_ROWS'
    value_range_body = {
          "range": "9Players!A1:J100",
          # "majorDimension": enum(Dimension),
          "values": [
            valuesArr
          ],
        }

    request = service.spreadsheets().values().append(spreadsheetId=spreadsheet_id, range=range_, valueInputOption=value_input_option, insertDataOption=insert_data_option, body=value_range_body)
    response = request.execute()

    pprint(response)


main()
