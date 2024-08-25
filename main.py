from linkedin_api import Linkedin
import os
import json
import csv
from dotenv import load_dotenv
from fuzzywuzzy import fuzz

load_dotenv()

api = Linkedin("yitzchakshapiro@gmail.com", "fuckCraigJones69!$")


def csv_to_json_obj(csvFilePath):
    data = []
    with open(csvFilePath, "r") as input_file:
        reader = csv.reader(input_file)

        for row in reader:
            if row:
                data.append(row[0])
    return data


def extract_profile_id_from_url(url):
    if not url:
        print("Warning: Empty URL encountered.")
        return None

    parts = url.strip().split("/")

    if len(parts) < 3:
        print(f"Warning: Malformed URL encountered: {url}")
        return None

    return parts[-2]


def get_company_descriptions(profile, company_name):
    descriptions = []
    for experience in profile.get("experience", []):
        if "companyName" in experience:
            if (
                fuzz.partial_ratio(
                    company_name.lower(), experience["companyName"].lower()
                )
                > 80
            ):
                description = experience.get("description", "").strip()
                if description:
                    descriptions.append(description)
    return descriptions


def main(csvFilePath, company_name, output_file_path):
    profile_urls = csv_to_json_obj(csvFilePath)
    all_descriptions = []

    for url in profile_urls:
        profile_id = extract_profile_id_from_url(url)
        if profile_id is None:
            continue  # Skip this URL if it's malformed or empty

        profile_info = api.get_profile(profile_id)
        descriptions = get_company_descriptions(profile_info, company_name)
        all_descriptions.extend(descriptions)

    # Filter out empty descriptions
    all_descriptions = [desc for desc in all_descriptions if desc]

    # Write descriptions to a text file
    with open(output_file_path, "w") as output_file:
        for description in all_descriptions:
            output_file.write(description + "\n")

    print(f"Descriptions written to {output_file_path}")


if __name__ == "__main__":
    csv_file_path = "connected.csv"
    company_name = "Scorpion"
    output_file_path = "descriptions.txt"

    main(csv_file_path, company_name, output_file_path)
