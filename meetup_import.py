import logging
from enum import Enum
from typing import Optional, Union

import re
import requests
import json
import unicodedata
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel
from ics import Calendar

# Banner paths
CODING_CLUB_BANNER = "/assets/images/events/event-coding-club-3.jpg"
WRITING_CLUB_BANNER = "/assets/images/events/event-writing-club.jpeg"




# ----- Models ------
class Image(BaseModel):
    path: str = "/assets/images/events/default.jpg"
    alt: str = "Square poster of event"

class WebLink(BaseModel):
    path: Optional[str]
    title: str = "View meetup event"
    target: str = "_target"

class MeetupEvents(BaseModel):
    title: str
    description: str
    category_style: Optional[str] = "tech-talk"
    category_name: Optional[str] = "Tech Talk"
    date: str
    expiration: Optional[str] = ""
    host: Optional[str] = ""
    speaker: Optional[str] = ""
    time: Optional[str] = ""
    image: Optional[Image]
    link: Optional[WebLink]


# ----- Helper function to clean bold/italics markdown from a name -----
def clean_name(s):
    s = re.sub(r'[*_~`]+', '', s)
    s = s.strip()
    s = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)
    if '|' in s:
        s = s.split('|')[0].strip()
    return s

# ----- Gets all hosts/co-hosts/speakers and formats accordingly -------
def get_hosts_and_speakers(event_desc: str) -> tuple[str, str]:
    hosts = []
    cohosts = []
    speakers = []

    text = event_desc.replace('\\', '')
    lines = text.splitlines()

    for line in lines:
        line = line.strip()

        host_match = re.match(r'\**Host:\**\s*(.+)', line, re.IGNORECASE)
        if host_match:
            host_name = clean_name(host_match.group(1))
            if host_name:
                hosts.append(host_name)
            continue

        cohost_match = re.match(r'\**Co-host:\**\s*(.+)', line, re.IGNORECASE)
        if cohost_match:
            cohost_name = clean_name(cohost_match.group(1))
            if cohost_name:
                cohosts.append(cohost_name)
            continue

        speaker_match = re.match(r'\**(Guest Presenter|Speaker):\**\s*(.+)', line, re.IGNORECASE)
        if speaker_match:
            speaker_name = clean_name(speaker_match.group(2))
            if speaker_name:
                speakers.append(speaker_name)
            continue

    speaker = ', '.join(speakers)
    host = ""

    if hosts and cohosts:
        host = f"{', '.join(hosts)} and {', '.join(cohosts)}"
    elif cohosts and not hosts:
        host = ', '.join(cohosts)
    else:
        host = ', '.join(hosts)

    return host, speaker

# ----- Removes all formatting, unicodes, emojis, etc from event description -----
def clean_description(text: str) -> str:
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'[*_~`]+', '', text)
    text = unicodedata.normalize('NFKD', text)
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        " \t\n\r"
        ".,;:!?'\"-()’"
    )
    text = ''.join(ch for ch in text if ch in allowed_chars)
    return text

# ----- Truncates event description to 1st sentence only and removes WCC prefix in sentence -----
def get_formatted_event_description(event_desc: str) -> str:
    full_description = (clean_description(event_desc) or "").strip()
    description = full_description.split("About Women Coding Community", 1)[0]
    print(f'{description=}')

    prefix = "Women Coding Community"
    if full_description.strip().startswith(prefix):
        return full_description.strip()[len(prefix):].lstrip()
    
    return description.strip()

# ------ Scrape a single Meetup event page to extract the main image URL ------
def get_event_image_url(url: str) -> str:
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    # Look for the Open Graph image tag first (most reliable)
    og_image = soup.find("meta", property="og:image")
    if og_image:
        return og_image.get("content")

    # Fallback
    img_tag = soup.find("img")
    if img_tag:
        image_url = img_tag.get("src")
    
    return image_url


# --- Main logic using downloaded iCal file ---
def get_upcoming_meetups_from_ical_file(ical_path: str) -> list[MeetupEvents]:
    with open(ical_path, "r", encoding="utf-8") as f:
        calendar = Calendar(f.read())

    # sort events to ensure order by event date
    sorted_events = sorted(calendar.events, key=lambda e: e.begin)

    upcoming_meetups: list[MeetupEvents] = []

    for event in sorted_events:
        title = event.name
        date_obj = event.begin.datetime
        expiration = date_obj.strftime("%Y%m%d")
        date = date_obj.strftime("%a, %b %d, %Y").upper()
        time = event.begin.datetime.strftime("%I:%M %p %Z")
        url = event.url or ""

        full_description = (event.description or "").strip()

        host, speaker = get_hosts_and_speakers(full_description)
        description = get_formatted_event_description(full_description)
        image_url = get_event_image_url(url)

        # Categorize event type
        category_style = "tech-talk"
        category_name = "Tech Talk"
        if "coding club" in description.lower():
            category_style = "coding-club"
            category_name = "Coding Club"
        elif "writing club" in description.lower():
            category_style = "writing-club"
            category_name = "Writing Club"
        elif "book club" in title.lower():
            category_style = "book-club"
            category_name = "Book Club"
        elif "career club" in title.lower():
            category_style = "career-club"
            category_name = "Career Club"
        elif "career talk" in description.lower():
            category_style = "career-talk"
            category_name = "Career Talk"

        upcoming_meetups.append(
            MeetupEvents(
                title=title,
                description=description.replace("\n", " "),
                category_style=category_style,
                category_name=category_name,
                date=date,
                time=time,
                expiration=expiration,
                host=host,
                speaker=speaker,
                image=Image(path=image_url, alt="WCC Meetup event image"),
                link=WebLink(path=url),
            )
        )
    return upcoming_meetups

# --- Processing and output ---
def process_meetup_data(meetup: dict) -> dict:
    # Convert all values to plain JSON-serializable types (strings)
    meetup["title"] = str(meetup.get("title", ""))
    meetup["description"] = str(meetup.get("description", "")).rstrip("\n")
    meetup["expiration"] = str(meetup.get("expiration", ""))
    meetup["host"] = str(meetup.get("host", ""))
    meetup["speaker"] = str(meetup.get("speaker", ""))
    if "image" in meetup and isinstance(meetup["image"], dict):
        meetup["image"]["path"] = str(meetup["image"].get("path", ""))
        meetup["image"]["alt"] = str(meetup["image"].get("alt", ""))
    if "link" in meetup and isinstance(meetup["link"], dict):
        meetup["link"]["path"] = str(meetup["link"].get("path", ""))
        meetup["link"]["title"] = str(meetup["link"].get("title", "View meetup event"))
    return meetup

# --- Create a unique key for an event using "title - date" ----
def get_event_key(event):
    return f"{event.get('title').strip()} - {event.get('date')}"

# --- Get a Set of keys for existing events ----
def get_existing_event_keys(events):
    return {get_event_key(e) for e in events}

# --- Get existing events in yml file ----
def load_existing_events_from_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return json.load(file) or []
    except FileNotFoundError:
        return []
    except (IOError, json.JSONDecodeError) as e:
        logging.error(f"Error reading file '{file_path}': {e}")
        return []

# ---- Appends specified data to yml file -----
def append_events_to_json_file(file_path, data):
    try:
        # Load existing events (if any), append new ones, then write full JSON array
        existing = load_existing_events_from_file(file_path) or []
        # Ensure incoming items are JSON-serializable dicts
        existing.extend(data)
        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(existing, file, ensure_ascii=False, indent=2)
    except (IOError, TypeError) as e:
        logging.error(f"Error writing new events to file '{file_path}': {e}")
        raise

# --- Script Start ---
def fetch_events():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    ical_file_path = "files/meetup.ics"
    json_file_path = "data/events.json"

    logging.info("Params: iCal URL: %s json: %s", ical_file_path, json_file_path)
    upcoming_events = get_upcoming_meetups_from_ical_file(ical_file_path)

    existing_events = load_existing_events_from_file(json_file_path)
    existing_keys = get_existing_event_keys(existing_events)
    added_events = []
    
    logging.info("Upcoming Meetup Events:")
    for event in upcoming_events:
        
        logging.info(f"{event.title}")
        formatted_event = process_meetup_data(event.model_dump())
        event_key = get_event_key(formatted_event)

        if event_key not in existing_keys:
            added_events.append(formatted_event)
            existing_keys.add(event_key)
        else:
            logging.info(f"{event_key} already exists in events.yml")

    if len(added_events) > 0:
        append_events_to_json_file(json_file_path, added_events)
        logging.info(f"Added {len(added_events)} new event(s) to events.json.")
    else:
        logging.info("No new events to add.")


if __name__ == "__main__":
    fetch_events()
