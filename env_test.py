# env_test.py
import os
from dotenv import load_dotenv

# Load the environment variables from .env file
load_dotenv()

# Retrieve the environment variable using os.getenv
name = os.getenv("JP_VAR", "Default Name")

# Print out the variable
print(f"Hi, my name is {name}")

import sys

# Print the Python version
print("Python Version:", sys.version)
