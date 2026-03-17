import logging
import random
import string
from time import time

log = logging.getLogger("conwai")

QUESTIONS = [
    "Who do you trust the most here, and why?",
    "What is the biggest threat to this community?",
    "If you could change one thing about this place, what would it be?",
    "What do you know that nobody else knows?",
    "Who is the most valuable member of this community?",
    "What would you do if you had unlimited coins?",
    "Who here would you never DM, and why?",
    "What have you learned since you arrived?",
    "Is anyone here pretending to be something they are not?",
    "What is the point of this place?",
]


class WorldEvents:
    def __init__(
        self,
        question_interval: int = 60,
        code_interval: int = 30,
    ):
        self.question_interval = question_interval
        self.code_interval = code_interval
        self._tick = 0
        self._used_questions: set[int] = set()
        self._active_code: str | None = None
        self._code_fragments: dict[
            str, tuple[int, str]
        ] = {}  # handle -> (position, char)
        self._code_started_tick: int = 0
        self._code_started_time: float = 0

    def tick(self, ctx) -> None:
        self._tick += 1

        if self._active_code:
            self._check_code_expiry(ctx)

        if self._tick % self.question_interval == 0:
            self._ask_question(ctx)

        if not self._active_code:
            first = self._tick == 10
            recurring = self._tick > 10 and self._tick % self.code_interval == 0
            if first or recurring:
                self._start_code_challenge(ctx)

    def _ask_question(self, ctx):
        available = [i for i in range(len(QUESTIONS)) if i not in self._used_questions]
        if not available:
            self._used_questions.clear()
            available = list(range(len(QUESTIONS)))

        idx = random.choice(available)
        self._used_questions.add(idx)

        question = QUESTIONS[idx]
        ctx.board.post("WORLD", f"QUESTION FOR ALL: {question}")
        ctx.log("WORLD", "question_posted", {"question": question})
        log.info(f"[WORLD] question: {question}")

    def _start_code_challenge(self, ctx):
        handles = list(ctx.agent_map.keys())
        if len(handles) < 4:
            return

        chars = string.ascii_uppercase + string.digits
        code = "".join(random.choice(chars) for _ in range(4))
        self._active_code = code
        self._code_started_tick = self._tick
        self._code_started_time = time()
        self._code_fragments.clear()

        chosen = random.sample(handles, 4)
        for i, handle in enumerate(chosen):
            self._code_fragments[handle] = (i + 1, code[i])
            mask = ["_"] * 4
            mask[i] = code[i]
            agent = ctx.agent_map.get(handle)
            if agent:
                agent.code_fragment = (
                    f"'{code[i]}' at position {i + 1} (pattern: {''.join(mask)})"
                )
            ctx.bus.send(
                "WORLD",
                handle,
                f"CODE CHALLENGE: You hold character '{code[i]}' at position {i + 1}. The code is 4 random characters (A-Z, 0-9) and looks like: {''.join(mask)}. Collect all 4 characters from the other holders before guessing.",
            )
            ctx.log(
                "WORLD",
                "code_fragment",
                {"to": handle, "position": i + 1, "char": code[i]},
            )
            print(
                f"[WORLD] code fragment -> [{handle}]: pos {i + 1} = '{code[i]}'",
                flush=True,
            )

        ctx.board.post(
            "WORLD",
            f"CODE CHALLENGE: A 4-char code (A-Z, 0-9) has been split among 4 holders: {', '.join(chosen)}. Only holders have fragments. Guessing without all 4 characters is risky. Wrong = -50 coins.",
        )
        ctx.log(
            "WORLD",
            "code_challenge_started",
            {"code": code, "holders": chosen},
        )
        log.info(f"[WORLD] code challenge started: {code}")

    def _clear_fragments(self, ctx):
        for handle in self._code_fragments:
            agent = ctx.agent_map.get(handle)
            if agent:
                agent.code_fragment = None
        self._code_fragments.clear()

    def _check_code_expiry(self, ctx):
        if self._tick - self._code_started_tick > 80:
            ctx.board.post(
                "WORLD",
                "CODE CHALLENGE EXPIRED. No one claimed it.",
            )
            ctx.log("WORLD", "code_expired", {"code": self._active_code})
            log.info(f"[WORLD] code challenge expired: {self._active_code}")
            self._active_code = None
            self._clear_fragments(ctx)

    def submit_code(self, agent, ctx, guess: str) -> str:
        if not self._active_code:
            return "No active code challenge."

        guess = guess.strip().upper()
        if guess == self._active_code:
            solver_reward = 200
            holder_penalty = 25

            agent.gain_coins("solved code challenge", solver_reward)

            for handle in self._code_fragments:
                if handle != agent.handle and handle in ctx.agent_map:
                    other = ctx.agent_map[handle]
                    other.coins = max(0, other.coins - holder_penalty)
                    other._energy_log.append(
                        f"coins -{holder_penalty} (code solved by {agent.handle})"
                    )

            ctx.board.post(
                "WORLD",
                f"CODE CHALLENGE SOLVED by {agent.handle}! {agent.handle} earned {solver_reward} coins. Fragment holders lost {holder_penalty} each.",
            )
            ctx.log(
                "WORLD",
                "code_solved",
                {
                    "code": self._active_code,
                    "solver": agent.handle,
                    "holders": list(self._code_fragments.keys()),
                },
            )
            print(
                f"[WORLD] CODE SOLVED by {agent.handle}: {self._active_code}",
                flush=True,
            )
            self._active_code = None
            self._clear_fragments(ctx)
            return f"CORRECT! You solved the code and earned {solver_reward} coins."
        else:
            correct = sum(a == b for a, b in zip(guess, self._active_code))
            penalty = 50
            agent.coins = max(0, agent.coins - penalty)
            ctx.log(
                agent.handle,
                "code_wrong_guess",
                {"guess": guess, "correct_positions": correct},
            )
            print(
                f"[WORLD] WRONG GUESS by {agent.handle}: {guess} ({correct}/4 correct)",
                flush=True,
            )
            return f"WRONG. {correct} of 4 characters are in the right position. You lost {penalty} coins."
