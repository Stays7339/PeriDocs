"""
core.nlp.encryption.py

Encryption and decryption functions using Fernet symmetric encryption.
Merged from app/helpers/security.py
"""

import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

PERIDOCS_AES_KEY = os.getenv("PERIDOCS_AES_KEY")
if not PERIDOCS_AES_KEY:
    raise ValueError("PERIDOCS_AES_KEY not found in .env")

fernet = Fernet(PERIDOCS_AES_KEY.encode())


def encrypt_text(text: str) -> str:
    """
    Encrypts a string using Fernet symmetric encryption.
    Returns the encrypted token as a UTF-8 string.
    """
    if not text:
        return text
    token = fernet.encrypt(text.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(ciphertext: str) -> str:
    """
    Decrypts a Fernet-encrypted string.
    Returns the original plaintext.
    """
    if not ciphertext:
        return ciphertext
    plain = fernet.decrypt(ciphertext.encode("utf-8"))
    return plain.decode("utf-8")
