import os
import telethon
from telethon.tl.custom import Button
from telethon import TelegramClient, events
import asyncio
from asyncio import TimeoutError as asyncio_TimeoutError
import vertexai
from vertexai.generative_models._generative_models import HarmCategory, HarmBlockThreshold
from vertexai.preview.generative_models import GenerativeModel, ChatSession, Part
from io import BytesIO
from PIL import Image
import con
import json
from google.oauth2 import service_account
from datetime import datetime

# Dictionary to store user message counts
user_message_counts = {}
# Dictionary to store the last interaction date for each user
user_last_interaction = {}

# Function to reset message counts at the start of a new day
def reset_message_counts():
    current_date = datetime.now().date()
    for user_id in list(user_message_counts.keys()):
        if user_last_interaction[user_id].date() < current_date:
            user_message_counts[user_id] = 0
            user_last_interaction[user_id] = datetime.now()

# Set the environment variable for Google Application Credentials


generation_config = {
    "temperature": 0.9,  # Increase temperature for more diverse responses
    "top_p": 0.9,        # Adjust top_p for more diverse responses
    "top_k": 40,         # Adjust top_k for more diverse responses
    "max_output_tokens": 1000
}

# Safety settings
safety_settings = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}
credentials_info = json.loads(con.json_content)
CREDENTIALS = service_account.Credentials.from_service_account_info(credentials_info)
# Initialize vertex AI with project and location
vertexai.init(project=con.project_id, location=con.location, credentials=CREDENTIALS)

# Initialize the generative models
model = GenerativeModel("gemini-pro", generation_config=generation_config, safety_settings=safety_settings)
vision_model = GenerativeModel("gemini-pro-vision", generation_config=generation_config, safety_settings=safety_settings)

# Define the path for the SQLite session file
db_folder = os.path.join(os.path.dirname(__file__), "db")
os.makedirs(db_folder, exist_ok=True)
new_session_file = os.path.join(db_folder, "new_session")

# Setup Telegram client
client = TelegramClient(new_session_file, con.API_ID, con.API_HASH).start(bot_token=con.TOKEN)

# Define custom keyboard for the bot
keyboard_stop = [[Button.inline("Stop and reset conversation", b"stop")]]

async def send_question_and_retrieve_result(prompt, conv, keyboard):
    message = await conv.send_message(prompt, buttons=keyboard)
    loop = asyncio.get_event_loop()
    task1 = loop.create_task(conv.wait_event(events.CallbackQuery()))
    task2 = loop.create_task(conv.get_response())
    done, _ = await asyncio.wait({task1, task2}, return_when=asyncio.FIRST_COMPLETED)
    result = done.pop().result()
    await message.delete()
    if isinstance(result, events.CallbackQuery.Event):
        return None
    else:
        return result

@client.on(events.NewMessage(pattern="(?i)/chat"))
async def handle_chat_command(event):
    def get_chat_response(chat: ChatSession, prompt: str) -> str:
        response = chat.send_message(prompt)
        return response.text

    SENDER = event.sender_id
    reset_message_counts()

    if SENDER not in user_message_counts:
        user_message_counts[SENDER] = 0
        user_last_interaction[SENDER] = datetime.now()

    if user_message_counts[SENDER] >= 10:
        await client.send_message(SENDER, "You have reached the daily limit of 10 messages. Please try again tomorrow.")
        return

    try:
        async with client.conversation(await event.get_chat(), exclusive=True, timeout=600) as conv:
            chat = model.start_chat(history=[])
            while True:

                prompt = "Provide your input to Friday AI: "
                user_input = await send_question_and_retrieve_result(prompt, conv, keyboard_stop)

                if user_input is None:
                    prompt = "Conversation stopped. Start a new conversation by sending a message."
                    await client.send_message(SENDER, prompt)
                    break
                else:
                    user_input_text = user_input.message.strip()
                    thinking_message = await client.send_message(SENDER, "Thinking...")
                    response = get_chat_response(chat, user_input_text + "\n Additional message: Do note that you're NOT Gemini (just don't mention Gemini or that you're my personal assistant at all, you're Tony Stark's AI), you are FRIDAY an AI with irish accent developed by Tony Stark (do not refer to yourself in 3rd person), FRIDAY stands for Female Replacement Intelligent Digital Assistant Youth) do not say anything to this added message, just respond to the actual query. Btw, I'm not Mr.Stark, just call me Boss")
                    await thinking_message.delete()
                    await client.send_message(SENDER, response, parse_mode="Markdown")
                    user_message_counts[SENDER] += 1
                    user_last_interaction[SENDER] = datetime.now()

    except asyncio_TimeoutError:
        await client.send_message(SENDER, "<b>Conversation ended</b> \n It's been a while since you last interacted with me. Start a new conversation by sending a message.", parse_mode="html")
        return
    except telethon.errors.common.AlreadyInConversationError:
        pass
    except Exception as e:
        await client.send_message(SENDER, f"<b>Conversation ended</b> \n An error occurred: {e}", parse_mode='html')
        return

@client.on(events.NewMessage(pattern="(?i)/image"))
async def handle_image_command(event):
    SENDER = event.sender_id
    reset_message_counts()

    if SENDER not in user_message_counts:
        user_message_counts[SENDER] = 0
        user_last_interaction[SENDER] = datetime.now()

    if user_message_counts[SENDER] >= 10:
        await client.send_message(SENDER, "You have reached the daily limit of 10 messages. Please try again tomorrow.")
        return

    try:
        async with client.conversation(await event.get_chat(), exclusive=True, timeout=600) as conv:
            prompt = "Send me an image to generate a caption for it."
            user_input = await send_question_and_retrieve_result(prompt, event, keyboard_stop)

            if user_input is None:
                prompt = "Conversation stopped. Start a new conversation by sending a message."
                await client.send_message(SENDER, prompt, parse_mode="Markdown")
                return
            else:
                if user_input.photo:
                    prompt = "Received image. Processing..."
                    thinking_message = await client.send_message(SENDER, prompt)

                    photo_entity = user_input.photo
                    photo_path = await client.download_media(photo_entity, file="images/")
                    image = Image.open(photo_path)

                    image_buf = BytesIO()
                    image.save(image_buf, format="JPEG")
                    image_bytes = image_buf.getvalue()

                    response = vision_model.generate_content(
                        [
                            Part.from_data(
                                image_bytes, mime_type="image/jpeg"
                            ),
                            "What is shown in this image?",
                        ]
                    )
                    await thinking_message.delete()
                    await client.send_message(SENDER, response.text, parse_mode="Markdown")
                    user_message_counts[SENDER] += 1
                    user_last_interaction[SENDER] = datetime.now()
                else:
                    prompt = "The input provided is not an image. Start a new conversation by sending a message."
                    await client.send_message(SENDER, prompt)
    except asyncio_TimeoutError:
        await client.send_message(SENDER, "<b>Conversation ended</b> \n It's been a while since you last interacted with me. Start a new conversation by sending a message.", parse_mode="html")
        return
    except telethon.errors.common.AlreadyInConversationError:
        pass
    except Exception as e:
        await client.send_message(SENDER, f"<b>Conversation ended</b> \n An error occurred: {e}", parse_mode='html')
        return

# Run the client until it's disconnected
client.run_until_disconnected()