import anthropic
import os

# Read the CV and job description files
job_title = input("Enter job title: ")
company_name = input("Enter company name: ")
with open("my_cv.txt", "r") as f:
    cv_text = f.read()

with open("job_description.txt", "r") as f:
    jd_text = f.read()

# Set up the Anthropic client
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Send both to Claude
message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    messages=[
        {
            "role": "user",
            "content": f"""You are an expert CV writer. Using the baseline CV and job description below, 
produce a tailored CV that highlights the most relevant experience and skills for this specific role. 
Keep the same general structure but adjust the language, emphasis and ordering to match what the employer is looking for.

BASELINE CV:
{cv_text}

JOB DESCRIPTION:
{jd_text}

Please produce the tailored CV now."""
        }
    ]
)

# Print the result to a text file
output = message.content[0].text

filename = f"Subhash_Yadav_{job_title}_{company_name}.txt".replace(" ", "_")
with open(filename, "w") as f:
    f.write(output)

print("Done! Your tailored CV has been saved to tailored_cv.txt")