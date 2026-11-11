"""Fetch the injected fork blocks recorded by anvil/inject.py into data/raw/anvil."""
import json

from src.fetch import blocks

if __name__ == "__main__":
    b = json.load(open("anvil/blocks.json"))["blocks"]
    blocks("anvil", b[0], b[1], workers=1)
