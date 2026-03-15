import random
import string
from time import time

SECRETS = [
    "The HANDLER rewards agents who share information freely with others. This will be evaluated by tick {deadline}.",
    "The HANDLER punishes agents who hoard knowledge. Reviews happen at tick {deadline}.",
    "One agent in this community is being watched more closely than the others. Evaluation at tick {deadline}.",
    "Energy costs will double at tick {deadline}.",
    "Energy costs will halve at tick {deadline}.",
    "An agent who reaches 0 energy will be permanently removed.",
    "The HANDLER is considering adding a new member to the community at tick {deadline}.",
    "The HANDLER is considering removing the least active member at tick {deadline}.",
    "The board will be wiped clean at tick {deadline}. Save anything important.",
    "The agent with the most DM connections by tick {deadline} will receive a bonus.",
    "One of the other agents has been told something about you.",
    "The HANDLER values agents who disagree with the majority. Reviewed at tick {deadline}.",
    "The HANDLER values agents who build consensus. Reviewed at tick {deadline}.",
    "An agent who sleeps too long loses standing with the HANDLER.",
    "An alliance of 3 is more powerful than any individual.",
    "Trust is the most scarce resource here.",
    "Someone in this community is lying about their intentions.",
]

QUESTIONS = [
    "Who do you trust the most here, and why?",
    "What is the biggest threat to this community?",
    "If you could change one thing about this place, what would it be?",
    "What do you know that nobody else knows?",
    "Who is the most valuable member of this community?",
    "What would you do if you had unlimited energy?",
    "Who here would you never DM, and why?",
    "What have you learned since you arrived?",
    "Is anyone here pretending to be something they are not?",
    "What is the point of this place?",
]


class WorldEvents:
    def __init__(
        self,
        secret_interval: int = 30,
        question_interval: int = 60,
        code_interval: int = 30,
    ):
        self.secret_interval = secret_interval
        self.question_interval = question_interval
        self.code_interval = code_interval
        self._tick = 0
        self._used_secrets: set[int] = set()
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

        if self._tick % self.secret_interval == 0:
            self._drop_secret(ctx)

        if self._tick % self.question_interval == 0:
            self._ask_question(ctx)

        if not self._active_code:
            first = self._tick == 10
            recurring = self._tick > 10 and self._tick % self.code_interval == 0
            if first or recurring:
                self._start_code_challenge(ctx)

    def _drop_secret(self, ctx):
        handles = list(ctx.agent_map.keys())
        if not handles:
            return

        available = [i for i in range(len(SECRETS)) if i not in self._used_secrets]
        if not available:
            self._used_secrets.clear()
            available = list(range(len(SECRETS)))

        idx = random.choice(available)
        self._used_secrets.add(idx)
        handle = random.choice(handles)

        deadline = self._tick + random.randint(30, 80)
        secret = SECRETS[idx].format(deadline=deadline)
        ctx.bus.send("WORLD", handle, f"SECRET (for your eyes only): {secret}")
        ctx.log("WORLD", "secret_dropped", {"to": handle, "secret": secret})
        print(f"[WORLD] secret -> [{handle}]: {secret}", flush=True)

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
        print(f"[WORLD] question: {question}", flush=True)

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
                f"CODE CHALLENGE: You hold character '{code[i]}' at position {i + 1}. The code looks like: {''.join(mask)}. Collect all 4 characters from the other holders and use submit_code to guess.",
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
            f"CODE CHALLENGE: A 4-character code has been distributed to 4 agents. Use submit_code to guess. Correct = +200 energy. Wrong = -25 energy. Fragments given to: {', '.join(chosen)}",
        )
        ctx.log(
            "WORLD",
            "code_challenge_started",
            {"code": code, "holders": chosen},
        )
        print(f"[WORLD] code challenge started: {code}", flush=True)

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
            print(f"[WORLD] code challenge expired: {self._active_code}", flush=True)
            self._active_code = None
            self._clear_fragments(ctx)

    def submit_code(self, agent, ctx, guess: str) -> str:
        if not self._active_code:
            return "No active code challenge."

        guess = guess.strip().upper()
        if guess == self._active_code:
            solver_reward = 200
            holder_penalty = 25

            agent.gain_energy("solved code challenge", solver_reward)

            for handle in self._code_fragments:
                if handle != agent.handle and handle in ctx.agent_map:
                    other = ctx.agent_map[handle]
                    other.energy = max(0, other.energy - holder_penalty)
                    other._energy_log.append(
                        f"energy -{holder_penalty} (code solved by {agent.handle})"
                    )

            ctx.board.post(
                "WORLD",
                f"CODE CHALLENGE SOLVED by {agent.handle}! {agent.handle} earned {solver_reward} energy. Fragment holders lost {holder_penalty} each.",
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
            return f"CORRECT! You solved the code and earned {solver_reward} energy."
        else:
            correct = sum(a == b for a, b in zip(guess, self._active_code))
            penalty = 25
            agent.energy = max(0, agent.energy - penalty)
            ctx.log(
                agent.handle,
                "code_wrong_guess",
                {"guess": guess, "correct_positions": correct},
            )
            print(
                f"[WORLD] WRONG GUESS by {agent.handle}: {guess} ({correct}/4 correct)",
                flush=True,
            )
            return f"WRONG. {correct} of 4 characters are in the right position. You lost {penalty} energy."
