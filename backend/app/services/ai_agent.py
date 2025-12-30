import os
from openai import OpenAI
from app.models import VideoAnalysis


class AIAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

    def _build_system_prompt(self, analysis: VideoAnalysis) -> str:
        """Build system prompt with video context."""
        refs_text = ""
        refs = analysis.references
        if any([refs.studies, refs.people, refs.books, refs.organizations, refs.terms]):
            refs_text = "\n\nEXTRACTED REFERENCES:\n"
            if refs.studies:
                refs_text += "Studies: " + ", ".join(refs.studies) + "\n"
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

        return f"""You are an AI assistant helping analyze and discuss a YouTube video.

VIDEO INFORMATION:
- Title: {analysis.video.title}
- Channel: {analysis.video.channel}
- Duration: {analysis.video.duration // 60} minutes
- URL: {analysis.video.url}
{refs_text}

TRANSCRIPT:
{transcript_preview}

Help the user understand, summarize, and discuss this video content. You can:
- Provide summaries at different levels of detail
- Answer questions about specific topics mentioned
- Explain scientific concepts or terms
- Highlight key takeaways and actionable advice
- Clarify who people mentioned are and their credentials
- Discuss the studies and research referenced

Be concise but thorough. Use the transcript to provide accurate information."""

    def summarize(self, analysis: VideoAnalysis) -> str:
        """Generate an AI summary of the video."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": self._build_system_prompt(analysis)
                },
                {
                    "role": "user",
                    "content": """Please provide a comprehensive summary of this video including:

1. **Overview** - What is this video about? (2-3 sentences)
2. **Key Findings** - Main points, data, and conclusions (bullet points)
3. **Practical Takeaways** - Actionable advice for the viewer (bullet points)
4. **Notable References** - Important studies, people, or concepts mentioned with brief context

Format the response in Markdown."""
                }
            ],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content

    def chat(
        self,
        analysis: VideoAnalysis,
        messages: list[dict],
        user_message: str
    ) -> str:
        """Chat about the video with conversation history."""
        chat_messages = [
            {
                "role": "system",
                "content": self._build_system_prompt(analysis)
            }
        ]

        # Add conversation history
        for msg in messages:
            chat_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # Add new user message
        chat_messages.append({
            "role": "user",
            "content": user_message
        })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=chat_messages,
            temperature=0.7,
            max_tokens=1500
        )
        return response.choices[0].message.content
