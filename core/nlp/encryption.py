"""
core.nlp.encryption.py
save-state updated 202512111404
"""
import os
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv
import asyncio

load_dotenv()

PERIDOCS_AES_KEY = os.getenv("PERIDOCS_AES_KEY")
if not PERIDOCS_AES_KEY:
    raise ValueError("PERIDOCS_AES_KEY not found in .env")

fernet = Fernet(PERIDOCS_AES_KEY.encode())

# -------------------------------
# ASYNC ENCRYPTION / DECRYPTION
# -------------------------------

async def encrypt_text(text: str) -> str:
    """
    Asynchronously encrypt a string using Fernet.
    Returns the encrypted token as a UTF-8 string.
    """
    if not text:
        return text
    token = await asyncio.to_thread(fernet.encrypt, text.encode("utf-8"))
    return token.decode("utf-8")


async def decrypt_text(ciphertext: str) -> str:
    """
    Asynchronously decrypt a Fernet-encrypted string.
    Returns the original plaintext.
    Handles invalid tokens gracefully.
    """
    if not ciphertext:
        return ciphertext
    try:
        plain = await asyncio.to_thread(fernet.decrypt, ciphertext.encode("utf-8"))
        return plain.decode("utf-8")
    except InvalidToken:
        return ""  # or log, depending on your error handling policy
