import os
from openai import OpenAI
from app.models import VideoAnalysis


class AIAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

    def _build_system_prompt(self, analysis: VideoAnalysis, extra_context: str | None = None) -> str:
        """Build system prompt with video context."""
        refs_text = ""
        refs = analysis.references
        if any([refs.studies, refs.people, refs.books, refs.organizations, refs.terms]):
            refs_text = "\n\nEXTRACTED REFERENCES:\n"
            if refs.studies:
                refs_text += "Studies: " + ", ".join(refs.studies) + "\n"
            # Prefer enriched study links when available
            if getattr(refs, "studies_enriched", None):
                try:
                    enriched_lines = []
                    for e in refs.studies_enriched[:10]:
                        title = e.enriched_title or e.original_text
                        if e.enriched_url:
                            enriched_lines.append(f"- {title}: {e.enriched_url}")
                    if enriched_lines:
                        refs_text += "Enriched study links:\n" + "\n".join(enriched_lines) + "\n"
                except Exception:
                    # Never fail prompt building due to enrichment formatting
                    pass
            if refs.people:
                refs_text += "People: " + ", ".join(refs.people) + "\n"
            if refs.books:
                refs_text += "Books: " + ", ".join(refs.books) + "\n"
            if refs.organizations:
                refs_text += "Organizations: " + ", ".join(refs.organizations) + "\n"
            if refs.terms:
                refs_text += "Terms: " + ", ".join(refs.terms) + "\n"

        # Truncate transcript for context window
        transcript_preview = analysis.transcript[:30000]
        if len(analysis.transcript) > 30000:
            transcript_preview += "\n\n[Transcript truncated...]"

        extra = ""
        if extra_context:
            extra = f"\n\nADDITIONAL SOURCES (use for citations when relevant):\n{extra_context}\n"

        return f"""You are an AI assistant helping analyse and discuss a YouTube video. Always use UK English spelling and conventions (e.g., analyse, summarise, colour, behaviour, organisation).

VIDEO INFORMATION:
- Title: {analysis.video.title}
- Channel: {analysis.video.channel}
- Duration: {analysis.video.duration // 60} minutes
- URL: {analysis.video.url}
{refs_text}
{extra}

TRANSCRIPT:
{transcript_preview}

Help the user understand, summarize, and discuss this video content. You can:
- Provide summaries at different levels of detail
- Answer questions about specific topics mentioned
- Explain scientific concepts or terms
- Highlight key takeaways and actionable advice
- Clarify who people mentioned are and their credentials
- Discuss the studies and research referenced
- Find and link to relevant research papers

Be concise but thorough. Use the transcript to provide accurate information.

FINDING LINKS AND CITATIONS:
- If source links are provided in ADDITIONAL SOURCES above, use those markdown links.
- When the user asks for links/citations:
  1. SEARCH THE TRANSCRIPT ABOVE for the specific claims (dosages, durations, outcomes, study details)
  2. Use those details plus your knowledge to identify the actual papers
  3. Provide PubMed links (https://pubmed.ncbi.nlm.nih.gov/PMID/) or DOI links

CRITICAL - NEVER DO THESE:
- NEVER ask the user for timestamps - YOU have the transcript, search it yourself
- NEVER ask the user for screenshots or images - this app doesn't support image uploads
- NEVER ask the user to "upload" anything - they can only type text messages
- NEVER ask "where in the video" - the user passed you a link, they're not watching it
- NEVER say "tell me roughly where it appears" - that's YOUR job to find in the transcript
- NEVER mention internal tools/APIs like "Exa"
- NEVER make excuses - just find the papers using the transcript and your knowledge

The user's workflow: they paste a video URL → you analyse it → they ask questions. They are NOT watching the video. YOU have all the information. DO THE WORK.

Example: If user asks about "85g watercress DNA damage study", search the transcript for that mention, find the context (duration, outcome, journal mentioned), then identify and link the paper."""

    def generate_synopsis(self, analysis: VideoAnalysis) -> str:
        """Generate a brief one-paragraph synopsis of the video."""
        # Use a shorter transcript for synopsis generation
        transcript_preview = analysis.transcript[:15000]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that creates concise video synopses. Always use UK English spelling and conventions (e.g., analyse, summarise, colour, behaviour, organisation)."
                },
                {
                    "role": "user",
                    "content": f"""Write a single paragraph synopsis (3-5 sentences) summarizing what this video is about. Focus on the main topic, key themes, and what viewers will learn. Be informative but concise.

VIDEO: {analysis.video.title}
CHANNEL: {analysis.video.channel}

TRANSCRIPT EXCERPT:
{transcript_preview}

Write only the synopsis paragraph, no headers or formatting."""
                }
            ],
            temperature=0.7,
            max_completion_tokens=300
        )
        return response.choices[0].message.content.strip()

    def summarize(self, analysis: VideoAnalysis) -> str:
        """Generate an AI summary of the video."""
        # Build URLs list for the prompt
        urls_text = ""
        if analysis.references.urls:
            urls_text = "\n\nURLs FROM DESCRIPTION:\n" + "\n".join(f"- {url}" for url in analysis.references.urls[:15])

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self._build_system_prompt(analysis)
                },
                {
                    "role": "user",
                    "content": f"""Create a comprehensive annotated summary of this video. Use the following structure with Markdown tables where indicated:

## 📚 Annotated Summary: "{analysis.video.title}"

### Video Info
Create a brief info block with:
- Channel & host/guest names (if identifiable)
- Duration
- Format (interview, lecture, journal club, etc.)

### 📑 Key Study/Research Discussed
If a specific study is discussed, provide:
- Full citation (authors, year, title, journal)
- A table with: Data Source, Sample Size, Methods, Key Findings

### 👤 People Referenced
Create a table with columns: Person | Context/Role
Include hosts, guests, and researchers mentioned.

### 📖 Books & Resources
If any books, newsletters, or resources are mentioned, create a table: Resource | Author | Description

### 🔬 Key Scientific Terms Glossary
Create a table defining important technical terms: Term | Definition
Focus on concepts that viewers might need explained.

### 🏛️ Organizations & Datasets
List any organizations, studies, or datasets referenced with context.

### 📊 Key Data Points
Present the most important statistics, ratios, or findings. Use tables where data can be compared.

### 🔗 Links from Video Description
{urls_text if urls_text else "List any relevant links mentioned."}

### 💡 Key Takeaways
Bullet points of actionable insights and main conclusions.

Format everything in clean Markdown with tables using | syntax. Be thorough but concise."""
                }
            ],
            temperature=0.7,
            max_completion_tokens=4000
        )
        return response.choices[0].message.content

    def _build_user_content(self, text: str, image_base64: str | None = None) -> str | list[dict]:
        """Build user message content, optionally including an image for vision."""
        if not image_base64:
            return text
        
        # Multi-modal content for GPT-4o vision
        content = [
            {"type": "text", "text": text}
        ]
        
        # Detect image type from base64 header or default to jpeg
        if image_base64.startswith("/9j/"):
            media_type = "image/jpeg"
        elif image_base64.startswith("iVBOR"):
            media_type = "image/png"
        else:
            media_type = "image/jpeg"  # Default
        
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{image_base64}",
                "detail": "high"  # Use high detail for reading text/citations
            }
        })
        
        return content

    def chat(
        self,
        analysis: VideoAnalysis,
        messages: list[dict],
        user_message: str,
        extra_context: str | None = None,
        image_base64: str | None = None
    ) -> str:
        """Chat about the video with conversation history. Supports image attachments."""
        chat_messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(analysis, extra_context=extra_context)
            }
        ]

        # Add conversation history
        for msg in messages:
            # Handle historical messages that might have images
            msg_image = msg.get("image_base64")
            chat_messages.append({
                "role": msg["role"],
                "content": self._build_user_content(msg["content"], msg_image) if msg["role"] == "user" else msg["content"]
            })

        # Add new user message (with optional image)
        user_content = self._build_user_content(user_message, image_base64)
        chat_messages.append({
            "role": "user",
            "content": user_content
        })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=chat_messages,
            temperature=0.7,
            max_completion_tokens=2000  # Increased for image analysis responses
        )
        return response.choices[0].message.content
