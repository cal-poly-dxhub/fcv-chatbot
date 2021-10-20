import sys
import json
import pymysql
from urllib.parse import unquote
from secret import get_creds
from twilio.twiml.messaging_response import Message, MessagingResponse

# If Twilio does not receive a response, it will not return a message.
# We can create an optional fallback webhook to create an error response.
# Or we can just create a generic error response in this lambda function.

try:
    db_credentials = json.loads(get_creds())
except Exception as e:
    print("could not obtain secret")
    sys.exit()

try:
    conn = pymysql.connect(
        host=db_credentials["host"],
        user=db_credentials["username"],
        password=db_credentials["password"],
        database=db_credentials["dbname"],
        connect_timeout=5
    )
    cur = conn.cursor()
except Exception as e:
    print("could not connect to the database")
    print(e)
    sys.exit()

# returns a response back to Twilio depending on user input


def lambda_handler(event, context):
    print("Logging event: {}".format(event))
    in_session = get_session(event['From'])
    return parse_user_response(in_session, event)


# generates an XML response using TwilioML package
def gen_response(msg_to_user):
    response = MessagingResponse()
    message = Message()
    message.body(msg_to_user)
    response.append(message)
    return "{}".format(response)


# Determines if a user is in a conversation with our chatbot.
# Phone_encoded is our url_encoded phone number from Twilio.
# We return a 3-tuple containing (phone #, inSession, lastResponse)
# inSession -> Bool, lastResponse -> 0-5 int.
def get_session(phone_encoded):
    sql_select = (
        "SELECT `Phone`, `InSession`, `LastResponse` FROM chatbot.Sessions WHERE Phone = %s")
    key = unquote(phone_encoded)
    cur.execute(sql_select, (key,))
    result = cur.fetchone()
    if not result:
        insert_session(phone_encoded)
    else:
        return result
    # user is now in session because we inserted.
    return (key, False, 0)


# Updates a user's session status to in_session and record the last_response.
def update_session(phone_encoded, in_session, last_response):
    try:
        sql_update = "UPDATE chatbot.Sessions SET `InSession`=%s, `LastResponse`=%s WHERE `Phone`=%s"
        cur.execute(sql_update, (in_session,
                    last_response, unquote(phone_encoded)))
        conn.commit()
    except:
        print("Could not insert into databse.")


# creates a `session` to indicate we are in our conversation.
def insert_session(phone_encoded):
    try:
        sql_insert = "INSERT INTO chatbot.Sessions (`Phone`, `InSession`, `LastResponse`) VALUES (%s, TRUE, 0)"
        cur.execute(sql_insert, unquote(phone_encoded))
        conn.commit()
        return True
    except Exception as e:
        print("Could not insert into database.")
    return False


# inserts our message into the db. If feedback option is selected, feedback_response
# should not be null.
def insert_message(feedback_type, metadata, feedback_response=None):
    try:
        sql_insert = """INSERT INTO 
                        chatbot.Messages 
                        (`Phone`, `FeedbackType`, `Feedback`, `FromZip`, 
                        `FromCountry`, `FromCity`, `FromState`,`SmsMessageId`, `SmsStatus`)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        sql_values = (unquote(metadata['From']), feedback_type, feedback_response,
                      metadata['FromZip'], unquote(
                          metadata['FromCountry']).replace("+", " "),
                      unquote(metadata['FromCity']).replace(
                          "+", " "), unquote(metadata['FromState']).replace("+", " "),
                      metadata['SmsSid'], metadata['SmsStatus'])
        cur.execute(sql_insert, sql_values)
        conn.commit()
    except Exception as e:
        print("Error: {}".format(e))
        print("Could not insert into db: {}. Feedback-type: {}\nResponse?: {}".format(
            metadata, feedback_type, feedback_response))


# determines the appropriate response to send back to the user.
# requires in_session bool value, and a Twilio event
# returns a TwilioML response.
def parse_user_response(in_session, event):
    # remove url/text encoding from user message
    user_response = unquote(event['Body']).replace("+", " ").strip().lower()
    print("Logging user response: {}".format(user_response))
    auto_response = ""
    # It would be ideal to store these responses in a db for easy changing
    if not in_session[1]:
        auto_response = """You’ve reached the feedback number of the KIRA project. Your feedback is valuable to us. What can I help you with?\n\nReply 1 for quality of services, 2 for doctors' availability, 3 for feedback related to medications, or 4 for any other types of feedback."""
        update_session(event['From'], True, 0)
        insert_message(0, event)
    elif user_response == "1":
        auto_response = "You've selected quality of service (1). This option is being worked on!"
        update_session(event['From'], False, int(user_response))
        insert_message(1, event)
    elif user_response == "2":
        auto_response = "You've selected doctor availability (2). This option is being worked on!"
        update_session(event['From'], False, int(user_response))
        insert_message(2, event)
    elif user_response == "3":
        auto_response = "You've selected medication feedback (3). Your medication feedback is important to us. Please describe your experience."
        update_session(event['From'], True, int(user_response))
        insert_message(3, event)
    elif user_response == "4":
        auto_response = "You've selected general feedback (4). Your feedback is important. Please describe your experience."
        update_session(event['From'], True, int(user_response))
        insert_message(4, event)
    else:
        # here we would get the user's last response. If it is a feedback response
        # we would store it in database. If it is not a feedback response,
        # we will mark as invalid.
        if in_session[2] == 3:
            auto_response = "Thank you for your feedback regarding medication. Goodbye!"
            update_session(event['From'], False, 0)
            insert_message(3, event, user_response)
        elif in_session[2] == 4:
            auto_response = "Thank you for your general feedback. Goodbye!"
            update_session(event['From'], False, 0)
            insert_message(4, event, user_response)
        else:
            auto_response = "We're sorry. That option is invalid. Please try again."
    twilio_response = gen_response(auto_response)
    print("Logging Twilio Response: {}".format(auto_response))
    return twilio_response
