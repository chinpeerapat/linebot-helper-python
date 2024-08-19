from linebot.models import (
    MessageEvent, TextSendMessage, QuickReply, QuickReplyButton, PostbackAction, PostbackEvent
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.aiohttp_async_http_client import AiohttpAsyncHttpClient
from linebot import (
    AsyncLineBotApi, WebhookParser
)
from fastapi import Request, FastAPI, HTTPException
import google.generativeai as genai
import os
import sys
from io import BytesIO

import aiohttp
import PIL.Image

from langtools import summarize_with_sherpa, summarize_text, generate_twitter_post
from gh_tools import summarized_yesterday_github_issues
from urllib.parse import parse_qs

# get channel_secret and channel_access_token from your environment variable
channel_secret = os.getenv('ChannelSecret', None)
channel_access_token = os.getenv('ChannelAccessToken', None)
gemini_key = os.getenv('GOOGLE_API_KEY')

imgage_prompt = '''
Describe all the information from the image in JSON format.
'''

if channel_secret is None:
    print('Specify ChannelSecret as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify ChannelAccessToken as environment variable.')
    sys.exit(1)
if gemini_key is None:
    print('Specify GEMINI_API_KEY as environment variable.')
    sys.exit(1)

# Initialize the FastAPI app for LINEBot
app = FastAPI()
session = aiohttp.ClientSession()
async_http_client = AiohttpAsyncHttpClient(session)
line_bot_api = AsyncLineBotApi(channel_access_token, async_http_client)
parser = WebhookParser(channel_secret)

namecard_path = "namecard"

# Initialize the Gemini Pro API
genai.configure(api_key=gemini_key)


@ app.post("/")
async def handle_callback(request: Request):
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = await request.body()
    body = body.decode()

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, PostbackEvent):
            # url parse query data from event.postback.data
            query_params = parse_qs(event.postback.data)
            print(f"query_params={query_params}")

            if query_params["action"] == "gen_tweet":
                # Get Msg ID
                message_id = query_params["m_id"]
                # Get message content
                message_content = line_bot_api.get_message_content(message_id)
                print(f"message_content={message_content}")
                result = generate_twitter_post(message_content)
                reply_msg = TextSendMessage(text=result)
                await line_bot_api.reply_message(
                    event.reply_token,
                    [reply_msg],
                )
                return 'OK'
        elif isinstance(event, MessageEvent):
            user_id = event.source.user_id

            # check if text is url
            if event.message.text.startswith("http"):
                result = summarize_with_sherpa(event.message.text)
                if len(result) > 2000:
                    result = summarize_text(result)
                reply_msg = TextSendMessage(text=result, quick_reply=QuickReply(
                    items=[QuickReplyButton(action=PostbackAction(label="gen_tweet", data="action=gen_tweet&m_id={event.message.id}"))]))
                await line_bot_api.reply_message(
                    event.reply_token,
                    [reply_msg],
                )
                return 'OK'
            elif event.message.text == "@g":
                result = summarized_yesterday_github_issues()
                reply_msg = TextSendMessage(text=result)
                await line_bot_api.reply_message(
                    event.reply_token,
                    [reply_msg],
                )
                return 'OK'

            msg = event.message.text
            reply_msg = TextSendMessage(text=f'uid: {user_id}, msg: {msg}')
            await line_bot_api.reply_message(
                event.reply_token,
                [reply_msg],
            )
        # elif isinstance(event, ImageEvent):
        #     message_content = await line_bot_api.get_message_content(
        #         event.message.id)
        #     image_content = b''
        #     async for s in message_content.iter_content():
        #         image_content += s
        #     img = PIL.Image.open(BytesIO(image_content))
        #     result = generate_json_from_image(img, imgage_prompt)
        #     print("------------IMAGE---------------")
        #     print(result.text)
        #     reply_msg = TextSendMessage(text=result.text)
        #     await line_bot_api.reply_message(
        #         event.reply_token,
        #         [reply_msg])
        #     return 'OK'
        else:
            continue
    return 'OK'


def generate_gemini_text_complete(prompt):
    """
    Generate a text completion using the generative model.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(prompt)
    return response


def generate_json_from_image(img, prompt):
    model = genai.GenerativeModel(
        'gemini-1.5-flash', generation_config={"response_mime_type": "application/json"})
    response = model.generate_content([prompt, img], stream=True)
    response.resolve()

    try:
        if response.parts:
            print(f">>>>{response.text}")
            return response
        else:
            print("No valid parts found in the response.")
            for candidate in response.candidates:
                print("!!!!Safety Ratings:", candidate.safety_ratings)
    except ValueError as e:
        print("Error:", e)
    return response
