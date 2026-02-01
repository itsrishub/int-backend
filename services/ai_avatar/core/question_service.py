"""
Real Question Generation Service integration.

Calls the actual question generation API at http://43.205.96.118
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# Base URL for the question generation service
QUESTION_SERVICE_BASE_URL = "http://43.205.96.118"


class QuestionType(str, Enum):
    """Types of interview questions."""
    INTRODUCTION = "introduction"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    TECHNICAL = "technical"
    CLOSING = "closing"
    GENERAL = "general"  # Default for questions from real API


@dataclass
class InterviewQuestion:
    """Represents an interview question."""
    id: int
    text: str
    type: QuestionType
    follow_up_hint: Optional[str] = None


@dataclass
class InterviewSessionInfo:
    """Information about an interview session from the real API."""
    session_id: int
    status: str
    user_id: Optional[str] = None


class QuestionService:
    """
    Service that integrates with the real Question Generation API.
    
    API Endpoints:
    - POST /api/generic/start_interview_session - Start interview
    - GET /api/theai/gen_ques/{session_id} - Get question
    - POST /api/theai/send_ans/ - Submit answer
    - POST /api/generic/end_interview_session - End interview
    """
    
    def __init__(self, base_url: str = QUESTION_SERVICE_BASE_URL):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        # Track session info: {session_id: InterviewSessionInfo}
        self._session_info: dict[str, InterviewSessionInfo] = {}
        # Track question counts: {session_id: questions_asked}
        self._questions_asked: dict[str, int] = {}
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def start_session(
        self,
        session_id: str,
        user_id: str = "default_user",
        start_time: Optional[str] = None,
        resume_blob: str = "",
        role: str = "",
        company: str = "",
        experience: int = 0,
        job_description: str = ""
    ) -> InterviewSessionInfo:
        """
        Start a new interview session with the real API.
        
        Args:
            session_id: Internal session ID (we'll get real session_id from API)
            user_id: User ID for the interview
            start_time: ISO 8601 format timestamp (defaults to now)
            resume_blob: Resume data
            role: Target role
            company: Target company
            experience: Years of experience
            job_description: Job description
            
        Returns:
            InterviewSessionInfo with the real session_id from API
        """
        if start_time is None:
            start_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        
        request_data = {
            "user_id": user_id,
            "start_time": start_time,
            "resume_blob": resume_blob,
            "role": role,
            "company": company,
            "experience": experience,
            "job_description": job_description
        }
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/generic/start_interview_session",
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        real_session_id = data["session_id"]
                        session_info = InterviewSessionInfo(
                            session_id=real_session_id,
                            status=data.get("status", "active"),
                            user_id=user_id
                        )
                        # Map internal session_id to real session_id
                        self._session_info[session_id] = session_info
                        self._questions_asked[session_id] = 0
                        logger.info(f"Started interview session: {session_id} -> real_session_id={real_session_id}")
                        return session_info
                    else:
                        raise Exception(f"API returned success=false: {data.get('message', 'Unknown error')}")
                else:
                    error_text = await response.text()
                    raise Exception(f"API error {response.status}: {error_text}")
        except Exception as e:
            logger.error(f"Failed to start interview session: {e}")
            raise
    
    def get_real_session_id(self, session_id: str) -> Optional[int]:
        """Get the real session_id from the API for an internal session_id."""
        session_info = self._session_info.get(session_id)
        return session_info.session_id if session_info else None
    
    async def get_next_question(
        self,
        session_id: str,
        previous_answer: Optional[str] = None
    ) -> Optional[InterviewQuestion]:
        """
        Get the next question from the real API.
        
        Args:
            session_id: Internal session ID
            previous_answer: The user's answer to the previous question (used by API for context)
            
        Returns:
            The next InterviewQuestion or None if interview is complete
        """
        real_session_id = self.get_real_session_id(session_id)
        if real_session_id is None:
            logger.error(f"Session {session_id} not found. Call start_session first.")
            return None
        
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/theai/gen_ques/{real_session_id}"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        question_id = data["question_id"]
                        question_text = data["question"]
                        questions_asked = data.get("questions_asked", 0)
                        
                        # Update question count
                        self._questions_asked[session_id] = questions_asked
                        
                        # Determine question type (API doesn't provide this, so we infer)
                        question_type = self._infer_question_type(question_text, data.get("is_first_question", False))
                        
                        question = InterviewQuestion(
                            id=question_id,
                            text=question_text,
                            type=question_type
                        )
                        
                        logger.info(f"Got question {question_id} for session {session_id} (questions_asked: {questions_asked})")
                        return question
                    else:
                        logger.warning(f"API returned success=false: {data}")
                        return None
                elif response.status == 404:
                    # Interview might be complete
                    logger.info(f"Question not found for session {real_session_id}, interview may be complete")
                    return None
                else:
                    error_text = await response.text()
                    logger.error(f"API error {response.status}: {error_text}")
                    raise Exception(f"API error {response.status}: {error_text}")
        except Exception as e:
            logger.error(f"Failed to get question: {e}")
            raise
    
    async def submit_answer(
        self,
        session_id: str,
        question_id: int,
        answer_text: str
    ) -> bool:
        """
        Submit an answer to the real API.
        
        Args:
            session_id: Internal session ID
            question_id: The question ID being answered
            answer_text: The user's answer
            
        Returns:
            True if answer was submitted successfully
        """
        request_data = {
            "question_id": question_id,
            "answer": answer_text
        }
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/theai/send_ans/",
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        logger.info(f"Submitted answer for question {question_id} in session {session_id}")
                        return True
                    else:
                        logger.warning(f"API returned success=false: {data.get('message', 'Unknown error')}")
                        return False
                else:
                    error_text = await response.text()
                    logger.error(f"API error {response.status}: {error_text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to submit answer: {e}")
            return False
    
    async def end_session(
        self,
        session_id: str,
        end_time: Optional[str] = None
    ) -> Optional[dict]:
        """
        End the interview session and get feedback.
        
        Args:
            session_id: Internal session ID
            end_time: ISO 8601 format timestamp (defaults to now)
            
        Returns:
            Feedback data from API or None if failed
        """
        real_session_id = self.get_real_session_id(session_id)
        if real_session_id is None:
            logger.error(f"Session {session_id} not found.")
            return None
        
        if end_time is None:
            end_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
        
        request_data = {
            "interview_session_id": real_session_id,
            "end_time": end_time
        }
        
        try:
            session = await self._get_session()
            async with session.post(
                f"{self.base_url}/api/generic/end_interview_session",
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("success"):
                        logger.info(f"Ended interview session {session_id} (real_session_id={real_session_id})")
                        # Cleanup
                        if session_id in self._session_info:
                            del self._session_info[session_id]
                        if session_id in self._questions_asked:
                            del self._questions_asked[session_id]
                        return data
                    else:
                        logger.warning(f"API returned success=false: {data.get('message', 'Unknown error')}")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"API error {response.status}: {error_text}")
                    return None
        except Exception as e:
            logger.error(f"Failed to end session: {e}")
            return None
    
    def get_question_by_id(self, question_id: int) -> Optional[InterviewQuestion]:
        """
        Get a question by ID.
        
        Note: The real API doesn't support this directly, so we return None.
        This is mainly for compatibility with existing code.
        """
        logger.warning("get_question_by_id not supported by real API")
        return None
    
    def get_total_questions(self) -> int:
        """
        Get total number of questions.
        
        Note: The real API doesn't provide a fixed total, so we return 0.
        Progress is tracked via questions_asked.
        """
        return 0  # Unknown total from real API
    
    def get_progress(self, session_id: str) -> tuple[int, int]:
        """
        Get the current progress in the interview.
        
        Returns:
            Tuple of (current_question_number, total_questions)
            total_questions is 0 since API doesn't provide it
        """
        questions_asked = self._questions_asked.get(session_id, 0)
        return (questions_asked, 0)  # Total unknown
    
    def is_interview_complete(self, session_id: str) -> bool:
        """
        Check if the interview is complete.
        
        Note: We can't determine this directly from the API.
        We infer completion when get_next_question returns None.
        """
        # This will be determined by get_next_question returning None
        return False
    
    def _infer_question_type(self, question_text: str, is_first_question: bool) -> QuestionType:
        """
        Infer question type from question text.
        
        The real API doesn't provide question type, so we infer it.
        """
        text_lower = question_text.lower()
        
        if is_first_question:
            return QuestionType.INTRODUCTION
        
        if any(word in text_lower for word in ["tell me about", "describe", "example", "time when"]):
            return QuestionType.BEHAVIORAL
        
        if any(word in text_lower for word in ["imagine", "if you", "what would you", "how would you"]):
            return QuestionType.SITUATIONAL
        
        if any(word in text_lower for word in ["explain", "what is", "how does", "define", "algorithm", "code"]):
            return QuestionType.TECHNICAL
        
        return QuestionType.GENERAL
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
