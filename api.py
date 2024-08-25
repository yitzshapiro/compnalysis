from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import json
import time
import os
import logging
from datetime import datetime, timedelta
from supabase import create_client, Client
from linkedin_api import Linkedin
from fuzzywuzzy import fuzz
import ollama
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

logging.basicConfig(
    level=logging.INFO,
    filename="app.log",
    filemode="a",
)

apollo_api_key = os.environ.get("APOLLO_API_KEY")
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(url, key)


@app.route('/api/get_orgs', methods=['POST'])
def get_orgs():
    data = request.json
    org_name = data.get('org_name', '')

    def generate():
        yield "data: Searching for organizations...\n\n"

        url = "https://api.apollo.io/api/v1/mixed_companies/search"
        payload = {
            "page": 1,
            "per_page": 10,
            "q_organization_name": org_name
        }
        headers = {
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/json',
            'X-Api-Key': apollo_api_key
        }

        logging.debug(f"Payload being sent: {json.dumps(payload)}")

        try:
            response = requests.post(url, headers=headers, json=payload)
            logging.debug(f"Response: {response.text}")
            response.raise_for_status()

            response_data = response.json()
            accounts = response_data.get('accounts', [])
            organizations = response_data.get('organizations', [])

            result = []
            for org in organizations:
                result.append({
                    "name": org.get("name"),
                    "id": org.get("id"),
                    "linkedin_url": org.get("linkedin_url")
                })
            for account in accounts:
                result.append({
                    "name": account.get("name"),
                    "id": account.get("organization_id"),  # Use organization_id for accounts
                    "linkedin_url": account.get("linkedin_url")
                })
            
            yield f"data: Found {len(result)} organizations.\n\n"
            yield f"data: {json.dumps(result)}\n\n"

        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
            yield f"data: Error: HTTP error occurred - {http_err}\n\n"
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Request exception occurred: {req_err}")
            yield f"data: Error: Request exception occurred - {req_err}\n\n"
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            yield f"data: Error: An unexpected error occurred - {e}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/get_people', methods=['POST'])
def get_people():
    data = request.json
    org_id = data.get('org_id')
    person_titles = data.get('person_titles', [])

    def generate():
        yield "data: Searching for people...\n\n"

        url = "https://api.apollo.io/v1/mixed_people/search"
        linkedin_profiles = []
        page = 1
        partial_results_only = True

        try:
            while partial_results_only:
                payload = {
                    "organization_ids": [org_id],
                    "page": page,
                    "per_page": 100,
                    "person_titles": person_titles
                }
                headers = {
                    'Cache-Control': 'no-cache',
                    'Content-Type': 'application/json',
                    'X-Api-Key': apollo_api_key
                }

                yield f"data: Sending request for page {page}...\n\n"
                response = requests.post(url, headers=headers, json=payload)
                logging.debug(f"Response: {response.text}")
                response.raise_for_status()

                response_data = response.json()
                yield f"data: Received response for page {page}...\n\n"

                people = response_data.get('people', [])
                yield f"data: Found {len(people)} people on page {page}...\n\n"

                if people:
                    for person in people:
                        linkedin_profiles.append({
                            'linkedin_url': person.get('linkedin_url'),
                            'first_name': person.get('first_name'),
                            'last_name': person.get('last_name'),
                            'title': person.get('title')
                        })
                    page += 1
                    partial_results_only = response_data.get('partial_results_only', False)
                else:
                    partial_results_only = False

            if linkedin_profiles:
                yield f"data: {json.dumps(linkedin_profiles)}\n\n"
            else:
                yield "data: No results found.\n\n"

        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred: {http_err}")
            yield f"data: Error: HTTP error occurred - {http_err}\n\n"
        except requests.exceptions.RequestException as req_err:
            logging.error(f"Request exception occurred: {req_err}")
            yield f"data: Error: Request exception occurred - {req_err}\n\n"
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            yield f"data: Error: An unexpected error occurred - {e}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route("/api/get_linkedin_descriptions", methods=["POST"])
def get_linkedin_descriptions():
    data = request.json
    linkedin_urls = data.get("linkedin_urls", [])
    company_name = data.get("company_name")
    email = data.get("email")
    password = data.get("password")

    def generate():
        api = Linkedin(email, password)
        all_descriptions = []

        yield "data: Fetching LinkedIn profiles...\n\n"

        for url in linkedin_urls:
            profile_id = extract_profile_id_from_url(url)
            if not profile_id:
                continue

            profile = check_and_fetch_profile_from_supabase(profile_id)
            if profile:
                descriptions = get_company_descriptions(profile['profile_info'], company_name)
                all_descriptions.extend(descriptions)
                yield f"data: Loaded profile {profile_id} from cache...\n\n"
            else:
                profile_info = api.get_profile(profile_id)
                logging.info(f"Fetching from LinkedIn API: {profile_info}")
                descriptions = get_company_descriptions(profile_info, company_name)
                all_descriptions.extend(descriptions)

                save_profile_to_supabase(profile_id, profile_info)
                yield f"data: Processed profile {profile_id} and saved to cache...\n\n"

            # Log the descriptions for debugging
            logging.info(f"Descriptions for profile {profile_id}: {descriptions}")

            time.sleep(1)

        all_descriptions = [desc for desc in all_descriptions if desc]

        # Log all collected descriptions
        logging.info(f"All collected descriptions: {all_descriptions}")

        # Send all descriptions at once
        yield f"data: {json.dumps({'descriptions': all_descriptions})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


def check_and_fetch_profile_from_supabase(profile_id):
    """Check if the profile exists in Supabase and has been updated within the last 30 days."""
    try:
        response = (
            supabase.table("linkedin_profiles")
            .select("*")
            .eq("profile_id", profile_id)
            .execute()
        )
        logging.info(f"Supabase fetch response: {response}")
        if response.data:
            profile = response.data[0]
            last_updated = datetime.fromisoformat(profile["updated_at"].replace("Z", "+00:00"))
            if last_updated > datetime.utcnow() - timedelta(days=30):
                return profile
    except Exception as e:
        logging.error(f"Error fetching profile from Supabase: {e}")
    return None

def save_profile_to_supabase(profile_id, profile_info):
    """Save or update the profile information in Supabase."""
    try:
        existing_profile = (
            supabase.table("linkedin_profiles")
            .select("*")
            .eq("profile_id", profile_id)
            .execute()
        )
        
        if existing_profile.data:
            # Update existing profile
            data, error = supabase.table("linkedin_profiles").update({
                "profile_info": json.dumps(profile_info),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("profile_id", profile_id).execute()
        else:
            # Insert new profile
            data, error = supabase.table("linkedin_profiles").insert({
                "profile_id": profile_id,
                "profile_info": json.dumps(profile_info),
                "updated_at": datetime.utcnow().isoformat()
            }).execute()

        if error:
            logging.error(f"Error saving profile to Supabase: {error}")
        else:
            logging.info(f"Successfully saved profile {profile_id} to Supabase")
            logging.info(f"Saved data: {data}")

    except Exception as e:
        logging.error(f"Exception while saving profile to Supabase: {e}")

def get_company_descriptions(profile, company_name):
    descriptions = []
    try:
        for experience in profile.get("experience", []):
            if "companyName" in experience:
                if fuzz.partial_ratio(company_name.lower(), experience["companyName"].lower()) > 80:
                    description = experience.get("description", "").strip()
                    if description:
                        descriptions.append(description)
                    # Also include the job title
                    title = experience.get("title", "").strip()
                    if title:
                        descriptions.append(f"Job Title: {title}")
                    # We've found the relevant company, so we can break the loop
                    break
    except Exception as e:
        logging.error(f"Error extracting descriptions: {e}")
    
    logging.info(f"Extracted descriptions for {company_name} from profile: {descriptions}")
    return descriptions

def extract_profile_id_from_url(url):
    if not url:
        return None

    # Remove any query parameters
    url = url.split('?')[0]

    # Split the URL and get the last part
    parts = url.strip().split("/")
    
    # The profile ID is usually the last part of the URL
    profile_id = parts[-1]

    # If the last part is empty (URL ends with /), use the second to last
    if not profile_id and len(parts) > 1:
        profile_id = parts[-2]

    # Some URLs might contain 'in/' before the actual ID
    if profile_id == 'in':
        profile_id = parts[-1]

    return profile_id


@app.route("/api/summarize_profiles", methods=["POST"])
def summarize_profiles():
    data = request.json
    linkedin_urls = data.get("linkedin_urls", [])
    logging.debug(f"LinkedIn URLs: {linkedin_urls}")
    prompt = data.get("prompt", "")
    company_name = data.get("company_name", "")
    email = data.get("email", "")
    password = data.get("password", "")

    api = Linkedin(email, password)

    citation_map = {}
    all_descriptions = []

    for i, url in enumerate(linkedin_urls):
        profile_id = extract_profile_id_from_url(url)
        logging.debug(f"Processing profile ID: {profile_id}")
        if not profile_id:
            logging.warning(f"Invalid LinkedIn URL: {url}")
            continue

        profile = check_and_fetch_profile_from_supabase(profile_id)
        if not profile:
            try:
                profile_info = api.get_profile(profile_id)
                save_profile_to_supabase(profile_id, profile_info)
            except Exception as e:
                logging.error(f"Error fetching profile from LinkedIn: {e}")
                continue
        else:
            profile_info = json.loads(profile['profile_info'])

        descriptions = get_company_descriptions(profile_info, company_name)
        logging.debug(f"Descriptions for profile {profile_id}: {descriptions}")
        
        # Add name and current title to the descriptions
        name = f"{profile_info.get('firstName', '')} {profile_info.get('lastName', '')}".strip()
        current_title = profile_info.get('headline', '')
        if name or current_title:
            descriptions.insert(0, f"Name: {name}, Current Title: {current_title}")

        for j, desc in enumerate(descriptions):
            citation_number = f"<{i+1}.{j+1}>"
            citation_map[citation_number] = desc
            all_descriptions.append(f"{citation_number}: {desc}")

        time.sleep(1)  # To avoid rate limiting

    descriptions_with_citations = "\n".join(all_descriptions)
    logging.debug(f"Descriptions with citations: {descriptions_with_citations}")

    if not descriptions_with_citations:
        return jsonify({"error": "No relevant descriptions found for the given company and profiles."})

    summarized_content = summarize_text(descriptions_with_citations, prompt)

    return jsonify({"summary": summarized_content, "citations": citation_map})

def summarize_text(descriptions, prompt):
    response = ollama.chat(
        model="llama3.1:latest",
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that answers questions in a detailed manner based on a list of LinkedIn profile descriptions and cites its answers using the provided citation number in the following format: <citation_number> as in <1> or <4>.",
            },
            {
                "role": "user",
                "content": f"{descriptions}\n\nBased on the above list of descriptions (all from the same company), answer the question: {prompt}",
            },
        ],
    )
    return response["message"]["content"]


if __name__ == "__main__":
    # Verify Supabase connection
    try:
        supabase_response = supabase.table("linkedin_profiles").select("count", count="exact").execute()
        logging.info(f"Supabase connection successful. Row count: {supabase_response.count}")
    except Exception as e:
        logging.error(f"Error connecting to Supabase: {e}")
    
    app.run(debug=True)