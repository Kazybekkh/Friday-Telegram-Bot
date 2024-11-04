import telethon
from telethon.tl.custom import Button

from telethon import TelegramClient, events

import asyncio # provides infrastructure for writing asyncrhonus code eusing coroutines
from asyncio import TimeoutError as asyncio_TimeoutError
import vertexai

from vertexai.generative_models._generative_models import HarmCategory, HarmBlockThreshold
from vertexai.preview.generative_models import (
    GenerativeModel,
    ChatSession,
    Part
)

# imports for handling images and bytes
from io import BytesIO
from PIL import Image
import os
import con



generation_config = {
    "temperature": 0.7,
    "top_p": 1.0,
    "top_k": 1.0,
    "max_output_tokens": 100
}

# Safety settings
# Настройки безопасности для контроля порогов блокировки вредного контента
safety_settings = {
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
}
# initialize vertex AI with project and location
# ининциализация vertex AI с проектом и местоположением

vertexai.init(con.project_id, con.location)

# Initialize the generative models
# Инициализация генеративных моделей
model = GenerativeModel("gemini-pro", generation_config=generation_config, safety_settings=safety_settings)
vision_model = GenerativeModel("gemini-pro-vision", generation_config=generation_config, safety_settings=safety_settings)


# Настройка клиента telegram
client = TelegramClient(con.bot_session_name, con.API_ID, con.API_HASH).start(bot_token=con.TOKEN)


# Определение пользовательских шаблонов для бота
keyboard_stop = [[Button.inline("Stop and reset conversation", b"stop")]]

async def send_question_and_retrieve_result(prompt, conv, keyboard):
    # send the prompt with the keyboard to the user and store the sent message object
    message = await conv.send_message(prompt, buttons=keyboard)

    loop = asyncio.get_event_loop()

    # Create tasks to wait for the user to respond or tap a button
    task1 = loop.create_task(conv.wait_event(events.CallbackQuery()))
    task2 = loop.create_task(conv.get_response())

    # Wait for the user to respond or tap a button using asyncio.wait()
    done, _ = await asyncio.wait({task1, task2}, return_when=asyncio.FIRST_COMPLETED)

    # retrieve the result from the task that was completed coroutine and delete the sent message
    result = done.pop().result()
    await message.delete()

    # return the user's response or None if they tapped a button
    if isinstance(result, events.CallbackQuery.Event):
        return None
    else:
        return result



@client.on(events.NewMessage(pattern="(?i)/chat"))

async def handle_chat_command(event):
    def get_chat_response(chat: ChatSession, prompt: str) -> str:
        response = chat.send_message(prompt)
        return response.text

    # Get the sender ID
    SENDER = event.sender_id

    try:
        async with client.conversation(await event.get_chat(), exclusive=True, timeout = 600) as conv:
            # start a chat session
            chat = model.start_chat(history = [])
            # Keep asking for input and generating responses until the conversation times out or the user clicks the stop button

            while True:
                prompt = "Provide your input to Friday AI: "
                user_input = await send_question_and_retrieve_result(prompt, event, keyboard_stop)

                if user_input is None:
                    prompt = "Conversation stopped. Start a new conversation by sending a message."
                    await client.send_message(SENDER, prompt)
                    break

                else:
                    user_input = user_input.message.strip()
                    thinking_message = await client.send_message(SENDER, prompt)
                    # retrieve the response from Gemini
                    response = (get_chat_response(chat, user_input))

                    # delete the thinking message
                    await thinking_message.delete()
                    # send the response to the user

                    await client.send_message(SENDER, response, parse_mode = "Markdown")

    except asyncio_TimeoutError:
        await client.send_message(SENDER, "<b>Conversation ended</b> \n It's been a while since you last interacted with me. Start a new conversation by sending a message.", parse_mode = "html")
        return
    except telethon.errors.common.AlreadyInConversationError:
        pass
    except Exception as e:
        await client.send_message(SENDER, f"<b>Conversation ended</b> \n An error occurred: {e}", parse_mode='html')
        return

@client.on(events.NewMessage(pattern="(?i)/image"))
async def handle_image_command(event):
    SENDER = event.sender_id

    try:
        async with client.conversation(await event.get_chat(), exclusive=True, timeout = 600) as conv:
            prompt = "Send me an image to generate a caption for it."

            user_input = await send_question_and_retrieve_result(prompt, event, keyboard_stop)

            # checks if the user clicked the stop button
            if user_input is None:
                prompt = "Conversation stopped. Start a new conversation by sending a message."
                await client.send_message(SENDER, prompt, parse_mode = "Markdown")
                return
            else:
                if user_input.photo:
                    prompt = "Received image. Processing..."
                    thinking_message = await client.send_message(SENDER, prompt)

                    photo_entity = user_input.photo

                    # Download the image and open it using PIL
                    photo_path = await client.download_media(photo_entity, file = "images/")
                    image = Image.open(photo_path)

                    image_buf = BytesIO()
                    image.save(image_buf, format = "JPEG")
                    image_bytes = image_buf.getvalue()

                    # generate content using the vision model
                    response = vision_model.generate_content(
                        [
                            Part.from_data(
                                image_bytes, mime_type="image/jpeg"
                            ),
                            "What is shown in this image?",
                        ]
                    )
                    # Delete the thinking message
                    await thinking_message.delete()
                    # Send the response to the user
                    await client.send_message(SENDER, response.text, parse_mode = "Markdown")
                else:
                    prompt = "The input provided is not an image. Start a new conversation by sending a message."
                    await client.send_message(SENDER, prompt)
    except asyncio_TimeoutError:
        # Conversation timed out
        await client.send_message(SENDER, "<b>Conversation ended</b> \n It's been a while since you last interacted with me. Start a new conversation by sending a message.", parse_mode = "html")
        return
    except telethon.errors.common.AlreadyInConversationError:
        pass
    except Exception as e:
        await client.send_message(SENDER, f"<b>Conversation ended</b> \n An error occurred: {e}", parse_mode='html')
        return


