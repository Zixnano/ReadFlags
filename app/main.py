"""Read Flags pygame prototype: swipe deck, match list, chat room."""
import sys
import threading
import time
from pathlib import Path

import pygame

sys.path.insert(0, str(Path(__file__).resolve().parent))
import database  # noqa: E402
import engine  # noqa: E402

W, H = 800, 600
FPS = 60
TYPING_DELAY = 2.0

BG = (18, 18, 24)
PANEL = (32, 32, 42)
TEXT = (235, 235, 240)
MUTED = (150, 150, 165)
ACCENT = (255, 90, 120)
BUBBLE_ME = (60, 110, 220)
BUBBLE_THEM = (60, 60, 74)
GOOD = (80, 200, 120)
PALETTE = [(200, 90, 120), (90, 140, 210), (150, 110, 200), (220, 150, 80)]


def wrap_text(text, font, max_width):
    """Split text into lines that fit max_width pixels."""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for word in para.split(" "):
            if not word:
                continue
            while font.size(word)[0] > max_width:  # break very long words
                i = len(word)
                while i > 1 and font.size(word[:i])[0] > max_width:
                    i -= 1
                if cur:
                    lines.append(cur)
                    cur = ""
                lines.append(word[:i])
                word = word[i:]
            test = word if not cur else cur + " " + word
            if font.size(test)[0] <= max_width:
                cur = test
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


class Game:
    def __init__(self):
        pygame.init()
        pygame.key.set_repeat(400, 35)
        pygame.display.set_caption("Read Flags")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 18) or pygame.font.Font(pygame.font.get_default_font(), 18)
        self.font_small = pygame.font.SysFont("arial", 15)
        self.font_title = pygame.font.SysFont("arial", 26, bold=True)
        self.font_big = pygame.font.SysFont("arial", 56, bold=True)

        database.init_db()
        self.state = "swipe"          # swipe | list | chat
        self.histories = {}           # character_id -> [(sender, text)]
        self.chat_id = None
        self.input_text = ""
        self.pending = None           # reply being generated
        self.scroll = 0
        self.flash = None             # (message, until_time)
        self.chars = {}
        self.deck = []
        self.matches = []
        self.refresh()

    # ---------- data ----------

    def refresh(self):
        chars = engine.get_characters()
        self.chars = {c["id"]: c for c in chars}
        self.deck = [c for c in chars if not c["swiped"]]
        self.matches = [c for c in chars if c["matched"]]

    def swipe(self, liked):
        if not self.deck:
            return
        c = self.deck[0]
        engine.swipe(c["id"], liked)
        if liked:
            self.flash = (f"It's a match with {c['name']}!", time.time() + 1.6)
        self.refresh()

    def open_chat(self, index):
        if 0 <= index < len(self.matches):
            self.chat_id = self.matches[index]["id"]
            self.state = "chat"
            self.input_text = ""
            self.scroll = 0

    def send_message(self):
        text = self.input_text.strip()
        if not text or self.pending:
            return
        cid = self.chat_id
        hist = list(self.histories.setdefault(cid, []))[-8:]
        self.histories[cid].append(("player", text))
        self.input_text = ""
        self.scroll = 0
        box = {"done": False, "reply": ""}

        def work():
            try:
                box["reply"] = engine.process_message(cid, text, hist)
            except Exception:
                box["reply"] = "..."
            box["done"] = True

        threading.Thread(target=work, daemon=True).start()
        self.pending = {"cid": cid, "box": box, "land_at": time.time() + TYPING_DELAY}

    # ---------- events ----------

    def on_key(self, event):
        if self.state == "swipe":
            if event.key == pygame.K_RIGHT:
                self.swipe(True)
            elif event.key == pygame.K_LEFT:
                self.swipe(False)
            elif event.key == pygame.K_SPACE:
                self.state = "list"
            elif event.key == pygame.K_r and not self.deck:
                engine.reset_progress()
                self.histories.clear()
                self.pending = None
                self.refresh()
        elif self.state == "list":
            if event.key == pygame.K_SPACE:
                self.state = "swipe"
            elif event.unicode.isdigit() and event.unicode != "0":
                self.open_chat(int(event.unicode) - 1)
        elif self.state == "chat":
            if event.key == pygame.K_ESCAPE:
                self.state = "list"
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.send_message()
            elif event.key == pygame.K_BACKSPACE:
                self.input_text = self.input_text[:-1]
            elif event.unicode and event.unicode.isprintable() and len(self.input_text) < 300:
                self.input_text += event.unicode

    # ---------- update ----------

    def update(self):
        p = self.pending
        if p and p["box"]["done"] and time.time() >= p["land_at"]:
            self.histories.setdefault(p["cid"], []).append(("them", p["box"]["reply"]))
            self.pending = None
            if self.chat_id == p["cid"]:
                self.scroll = 0

    # ---------- drawing ----------

    def text(self, s, font, color, x, y, center=False):
        surf = font.render(s, True, color)
        rect = surf.get_rect()
        if center:
            rect.midtop = (x, y)
        else:
            rect.topleft = (x, y)
        self.screen.blit(surf, rect)
        return rect

    def draw_swipe(self):
        self.text("READ FLAGS", self.font_title, ACCENT, W // 2, 18, center=True)
        card = pygame.Rect(0, 0, 420, 450)
        card.center = (W // 2, 300)
        pygame.draw.rect(self.screen, PANEL, card, border_radius=18)
        if not self.deck:
            self.text("No more profiles.", self.font_title, TEXT, W // 2, 260, center=True)
            self.text("Press R to reset, SPACE for your matches.", self.font, MUTED, W // 2, 305, center=True)
        else:
            c = self.deck[0]
            color = PALETTE[(c["id"] - 1) % len(PALETTE)]
            cx, cy = W // 2, card.top + 100
            pygame.draw.circle(self.screen, color, (cx, cy), 65)
            initial = "?" if c["is_blind_profile"] else c["name"][0]
            surf = self.font_big.render(initial, True, (255, 255, 255))
            self.screen.blit(surf, surf.get_rect(center=(cx, cy)))
            self.text(f"{c['name']}, {c['age']}", self.font_title, TEXT, W // 2, cy + 85, center=True)
            self.text(c["job"], self.font, MUTED, W // 2, cy + 122, center=True)
            y = cy + 165
            for line in wrap_text(c["bio"], self.font, card.width - 60):
                self.text(line, self.font, TEXT, W // 2, y, center=True)
                y += self.font.get_linesize() + 2
        self.text("LEFT: pass      RIGHT: like      SPACE: matches", self.font, MUTED, W // 2, H - 60, center=True)
        self.text(f"Matches: {len(self.matches)}", self.font_small, MUTED, 20, 20)
        if self.flash and time.time() < self.flash[1]:
            banner = pygame.Rect(0, 0, 460, 70)
            banner.center = (W // 2, H // 2)
            pygame.draw.rect(self.screen, GOOD, banner, border_radius=14)
            self.text(self.flash[0], self.font_title, (10, 30, 15), W // 2, banner.top + 20, center=True)

    def draw_list(self):
        self.text("Matches", self.font_title, ACCENT, 40, 30)
        if not self.matches:
            self.text("No matches yet. Swipe right on someone.", self.font, MUTED, 40, 100)
        y = 100
        for i, c in enumerate(self.matches[:9]):
            row = pygame.Rect(40, y, W - 80, 70)
            pygame.draw.rect(self.screen, PANEL, row, border_radius=12)
            color = PALETTE[(c["id"] - 1) % len(PALETTE)]
            pygame.draw.circle(self.screen, color, (row.left + 40, row.centery), 24)
            self.text(f"[{i + 1}]  {c['name']}, {c['age']}", self.font, TEXT, row.left + 80, row.top + 12)
            hist = self.histories.get(c["id"])
            preview = hist[-1][1] if hist else "Say something..."
            if len(preview) > 60:
                preview = preview[:57] + "..."
            self.text(preview, self.font_small, MUTED, row.left + 80, row.top + 40)
            y += 80
        self.text("Press a number to open a chat      SPACE: back to swiping", self.font, MUTED, W // 2, H - 60, center=True)

    def draw_chat(self):
        cid = self.chat_id
        c = self.chars[cid]
        pygame.draw.rect(self.screen, PANEL, (0, 0, W, 60))
        self.text(f"{c['name']}, {c['age']}", self.font_title, TEXT, 20, 14)
        typing = bool(self.pending and self.pending["cid"] == cid)
        if typing:
            self.text("Typing...", self.font_small, GOOD, W - 100, 22)
        else:
            self.text("ESC: back", self.font_small, MUTED, W - 100, 22)

        area = pygame.Rect(20, 70, W - 40, H - 70 - 80)
        items = [("bio", c["bio"])] + list(self.histories.get(cid, []))
        if typing:
            items.append(("them", "Typing..."))
        max_w = 460
        lh = self.font.get_linesize()
        lhs = self.font_small.get_linesize()
        layout = []
        for kind, txt in items:
            if kind == "bio":
                lines = wrap_text(txt, self.font_small, area.width - 80)
                layout.append((kind, lines, len(lines) * lhs + 10))
            else:
                lines = wrap_text(txt, self.font, max_w - 24)
                layout.append((kind, lines, len(lines) * lh + 20))
        total = sum(h + 10 for _, _, h in layout)
        self.scroll = max(0, min(self.scroll, max(0, total - area.height)))

        prev_clip = self.screen.get_clip()
        self.screen.set_clip(area)
        y = area.bottom + self.scroll
        for kind, lines, h in reversed(layout):
            top = y - h
            if kind == "bio":
                ty = top + 5
                for line in lines:
                    self.text(line, self.font_small, MUTED, area.centerx, ty, center=True)
                    ty += lhs
            else:
                w = max(self.font.size(line)[0] for line in lines) + 24
                x = area.right - w if kind == "player" else area.left
                color = BUBBLE_ME if kind == "player" else BUBBLE_THEM
                pygame.draw.rect(self.screen, color, (x, top, w, h), border_radius=14)
                ty = top + 10
                for line in lines:
                    self.text(line, self.font, TEXT, x + 12, ty)
                    ty += lh
            y = top - 10
        self.screen.set_clip(prev_clip)

        box = pygame.Rect(20, H - 70, W - 40, 44)
        pygame.draw.rect(self.screen, PANEL, box, border_radius=12)
        shown = self.input_text
        while shown and self.font.size(shown)[0] > box.width - 30:
            shown = shown[1:]
        if shown:
            cursor = "|" if int(time.time() * 2) % 2 == 0 else ""
            self.text(shown + cursor, self.font, TEXT, box.left + 14, box.top + 11)
        else:
            self.text("Type a message and press ENTER", self.font, MUTED, box.left + 14, box.top + 11)

    def draw(self):
        self.screen.fill(BG)
        if self.state == "swipe":
            self.draw_swipe()
        elif self.state == "list":
            self.draw_list()
        else:
            self.draw_chat()

    # ---------- loop ----------

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    self.on_key(event)
                elif event.type == pygame.MOUSEWHEEL and self.state == "chat":
                    self.scroll += event.y * 30
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()


if __name__ == "__main__":
    Game().run()
