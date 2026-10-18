"""
Escale — versão para Pydroid 3

Para executar:
1. No Pydroid 3, instale o suporte ao Pygame caso ainda não esteja instalado.
2. Salve este arquivo como escale_pydroid3.py.
3. Abra o arquivo no Pydroid 3 e toque em Run.
"""

import pygame, random, math, os, sys, threading
import wave as wav_io
from array import array
from functools import lru_cache
from types import SimpleNamespace as NS

pygame.init()
W, H = 360, 600
ANDROID = (
    sys.platform == "android"
    or "ANDROID_ARGUMENT" in os.environ
    or "ANDROID_ROOT" in os.environ
    or "ANDROID_STORAGE" in os.environ
    or os.environ.get("PYDROID3") == "1"
)


def create_screen():
    if ANDROID:
        try:
            return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        except pygame.error:
            info = pygame.display.Info()
            width = max(1, info.current_w)
            height = max(1, info.current_h)
            return pygame.display.set_mode((width, height), pygame.FULLSCREEN)
    return pygame.display.set_mode((450, 750), pygame.RESIZABLE)


screen = create_screen()
pygame.display.set_caption("Escale")
if ANDROID:
    pygame.mouse.set_visible(False)

g = pygame.Surface((W, H)).convert()
clock = pygame.time.Clock()
sw = sh = 1
sc = 1.0
ox = oy = 0.0
scaled_size = (W, H)
scaled = None
dirty = True

# ---------- música e efeitos sonoros ----------
SAMPLE_RATE = 16000
MUSIC_FILE = "escale_musica_v2.wav"  # cache da música (gerada só na primeira vez)
audio = NS(
    available=False,
    music_enabled=True,
    effects_enabled=True,
    music_volume=0.32,
    effects_volume=0.75,
    music_channel=None,
    effect_channels=[],
    music_sound=None,
    effects={},
)


# Sintetizador simples: tudo é gerado por código, sem arquivos externos.
SINE_N = 2048
SINE = [math.sin(2 * math.pi * i / SINE_N) for i in range(SINE_N)]
MASK = SINE_N - 1


def w_sine(p):
    return SINE[int(p * SINE_N) & MASK]


def w_soft(p):
    # seno com um harmônico: timbre de "pluck" suave
    return 0.75 * SINE[int(p * SINE_N) & MASK] + 0.25 * SINE[int(p * 2 * SINE_N) & MASK]


def w_tri(p):
    return 4 * abs(p % 1.0 - 0.5) - 1


WAVES = {"sine": w_sine, "soft": w_soft, "tri": w_tri}


def add_tone(buf, start, freq, dur, amp, kind="soft", f_end=None,
             vib=0.0, vib_hz=12.0, power=2.0, wrap=False):
    """Soma uma nota (com glissando e vibrato opcionais) dentro de buf."""
    osc = WAVES[kind]
    n = int(SAMPLE_RATE * dur)
    size = len(buf)
    att = max(1, int(SAMPLE_RATE * 0.006))
    if f_end is None:
        f_end = freq
    phase = 0.0
    for i in range(n):
        k = i / n
        f = freq + (f_end - freq) * k
        if vib:
            f *= 1 + vib * SINE[int(i / SAMPLE_RATE * vib_hz * SINE_N) & MASK]
        phase += f / SAMPLE_RATE
        idx = start + i
        if idx >= size:
            if not wrap:
                break
            idx %= size
        buf[idx] += osc(phase) * min(1.0, i / att) * (1 - k) ** power * amp


def to_samples(buf, gain):
    peak = max(1e-9, max(abs(v) for v in buf))
    scale = gain * 32767 / peak
    samples = array("h", (int(v * scale) for v in buf))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def new_buf(seconds):
    return [0.0] * int(SAMPLE_RATE * seconds)


def sfx_sound(buf):
    return pygame.mixer.Sound(buffer=to_samples(buf, 0.8).tobytes())


def make_sfx():
    sr = SAMPLE_RATE
    # pulo: "pip" curto subindo
    jump = new_buf(0.16)
    add_tone(jump, 0, 300, 0.15, 0.8, "tri", f_end=620, power=1.5)
    # super pulo: varredura longa com brilho
    sj = new_buf(0.34)
    add_tone(sj, 0, 240, 0.32, 0.7, "tri", f_end=1000, power=1.2)
    add_tone(sj, int(sr * 0.04), 480, 0.28, 0.4, "sine", f_end=1500, vib=0.03, power=1.5)
    # poção: três notas de sino
    potion = new_buf(0.4)
    for j, f in enumerate((784, 988, 1319)):
        add_tone(potion, int(sr * 0.07 * j), f, 0.22, 0.6, "soft", power=2.5)
    # trampolim: "boing" descendo com tremido
    tramp = new_buf(0.36)
    add_tone(tramp, 0, 540, 0.34, 0.8, "soft", f_end=170, vib=0.12, vib_hz=22, power=1.3)
    # escudo salvando: subida brilhante
    rev = new_buf(0.45)
    add_tone(rev, 0, 330, 0.4, 0.7, "tri", f_end=990, power=1.0)
    add_tone(rev, int(sr * 0.1), 660, 0.3, 0.5, "soft", f_end=1320, vib=0.02, power=1.8)
    return {
        "revive": sfx_sound(rev),
        "jump": sfx_sound(jump),
        "super_jump": sfx_sound(sj),
        "potion": sfx_sound(potion),
        "trampoline": sfx_sound(tramp),
    }


def make_music_samples():
    """Música calma: baixo + arpejo + melodia suave (Lá menor, Fá, Dó, Sol)."""
    step = 0.25
    per_bar = 8
    chords = [
        (110.00, (220.00, 261.63, 329.63, 440.00)),
        (87.31, (174.61, 220.00, 261.63, 349.23)),
        (130.81, (261.63, 329.63, 392.00, 523.25)),
        (98.00, (196.00, 246.94, 293.66, 392.00)),
    ]
    pattern = (0, 2, 1, 3, 2, 1, 3, 2)
    buf = new_buf(step * per_bar * len(chords))
    for bar, (bass, notes) in enumerate(chords):
        t0 = bar * per_bar * step
        for half in (0, 4):
            add_tone(buf, int(SAMPLE_RATE * (t0 + half * step)), bass, step * 4,
                     0.55, "sine", power=0.9, wrap=True)
        for j, idx in enumerate(pattern):
            add_tone(buf, int(SAMPLE_RATE * (t0 + j * step)), notes[idx], step * 1.4,
                     0.28, "soft", power=2.5, wrap=True)
        for j, idx in ((0, 3), (4, 2)):
            add_tone(buf, int(SAMPLE_RATE * (t0 + j * step)), notes[idx] * 2, step * 3,
                     0.12, "tri", vib=0.004, power=1.5, wrap=True)
    return to_samples(buf, 0.4)


def save_wav(path, samples):
    with wav_io.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(samples.tobytes())


def sync_music():
    if not audio.available:
        return
    channel = audio.music_channel
    if audio.music_enabled and audio.music_volume > 0:
        if audio.music_sound is None:
            return
        channel.set_volume(audio.music_volume)
        if not channel.get_busy():
            channel.play(audio.music_sound, loops=-1)
    else:
        channel.stop()


def play_sfx(name):
    if not audio.available or not audio.effects_enabled or audio.effects_volume <= 0:
        return
    sound = audio.effects.get(name)
    if sound is None:
        return
    channel = next((ch for ch in audio.effect_channels if not ch.get_busy()), None)
    if channel is None and audio.effect_channels:
        channel = audio.effect_channels[0]
    if channel is not None:
        channel.set_volume(audio.effects_volume)
        channel.play(sound)


def change_volume(setting, amount):
    value = getattr(audio, setting)
    setattr(audio, setting, round(max(0.0, min(1.0, value + amount)), 2))
    sync_music()


def music_worker():
    """Carrega a música do cache; se não existir, gera e salva (só na 1ª vez)."""
    try:
        path = os.path.join(BASE, MUSIC_FILE)
        try:
            sound = pygame.mixer.Sound(path)
        except (pygame.error, OSError):
            samples = make_music_samples()
            sound = pygame.mixer.Sound(buffer=samples.tobytes())
            try:
                save_wav(path, samples)
            except (OSError, wav_io.Error):
                pass
        audio.music_sound = sound
        sync_music()
    except Exception:
        pass


def setup_audio():
    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
        pygame.mixer.set_num_channels(8)
        audio.effects = make_sfx()
        audio.music_channel = pygame.mixer.Channel(0)
        audio.effect_channels = [pygame.mixer.Channel(i) for i in range(1, 8)]
        audio.available = True
        # a música é preparada em segundo plano para o jogo abrir logo
        threading.Thread(target=music_worker, daemon=True).start()
    except (pygame.error, AttributeError):
        # Se o dispositivo não disponibilizar áudio, o jogo continua funcionando.
        audio.available = False


# ---------- ajustes fáceis ----------
JUMP = 11.8
SUPER_JUMP = 19.0
SUPER_CHARGES = 1
FLY_FRAMES = 300
ITEM_EVERY = (7, 11)
TRAMP_METROS = 20
TRAMP_CHANCE = 0.07
PARAISO_M = 20000

# Ajustes do pulo
JUMP_BUFFER = 9      # frames em que um toque antecipado ainda vale (~150 ms)
COYOTE = 6           # frames de tolerância após sair da plataforma
HOLD_JUMP = True     # True: segurar o botão de pulo quica sem precisar tocar de novo
GRAV = 0.45          # gravidade na subida (define a altura do pulo: não mexa)
FALL_G = 0.58        # gravidade na descida (maior = queda mais rápida e "firme")
MAX_FALL = 15        # velocidade máxima de queda
EDGE = 12            # meia-largura de pouso: perdoa pousos na borda da plataforma
LAND_TOL = 4         # tolerância vertical de pouso, em pixels

_G = GRAV
TRAMP_V = (_G + math.sqrt(_G * _G + 8 * _G * TRAMP_METROS * 10)) / 2


def layout():
    global screen, sw, sh, sc, ox, oy, scaled_size, scaled, dirty
    screen = pygame.display.get_surface()
    sw, sh = screen.get_size()
    sc = min(sw / W, sh / H)
    ox = (sw - W * sc) / 2
    oy = (sh - H * sc) / 2
    scaled_size = (max(1, int(W * sc)), max(1, int(H * sc)))
    # buffer reutilizado a cada frame (evita alocar uma superfície nova 60x por segundo)
    scaled = None if scaled_size == (W, H) else pygame.Surface(scaled_size).convert()
    dirty = True


layout()

# ---------- recorde ----------
try:
    BASE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    BASE = os.getcwd()

# No Android, use a writable app-home folder instead of the shared-storage
# folder where the script may have been opened from.
if ANDROID:
    android_home = os.path.expanduser("~")
    if android_home and os.path.isdir(android_home):
        BASE = android_home

RF = os.path.join(BASE, "escale_recorde.txt")

setup_audio()


def load_rec():
    try:
        with open(RF, encoding="utf-8") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def save_rec(v):
    try:
        with open(RF, "w", encoding="utf-8") as f:
            f.write(str(v))
    except OSError:
        # O jogo continua funcionando mesmo se o Pydroid bloquear a gravação.
        pass


# ---------- biomas ----------
def C(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


B = [
    dict(n="Floresta", t=C("#5fc98f"), b=C("#e6f7cb"), p=C("#7a4b2a"), g=C("#3f9d52"), pc=C("#ffffff"), dy=0.5),
    dict(n="Geleira", t=C("#86ccff"), b=C("#f0faff"), p=C("#8fd4ff"), g=C("#ffffff"), pc=C("#ffffff"), dy=1),
    dict(n="Nuvens", t=C("#ff9a73"), b=C("#ffe7b8"), p=C("#ffffff"), g=C("#ffc9d6"), pc=C("#ffffff"), dy=-0.25),
    dict(n="Vulcão", t=C("#2a0a0a"), b=C("#d9480f"), p=C("#2d1b16"), g=C("#ff8a1f"), pc=C("#ffb347"), dy=-1.1),
    dict(n="Espaço", t=C("#04051a"), b=C("#2b1760"), p=C("#6f7bff"), g=C("#b9c0ff"), pc=C("#ffffff"), dy=0),
    dict(n="Dimensão", t=C("#1d0533"), b=C("#0a6b7a"), p=C("#ff3df2"), g=C("#3ffcff"), pc=C("#3ffcff"), dy=0.3),
    dict(n="Paraíso", t=C("#ffd9f0"), b=C("#fff6c9"), p=C("#ffffff"), g=C("#ffd34d"), pc=C("#ffe27a"), dy=-0.35),
]

ITEM_COL = {
    "shield": (70, 150, 255),
    "super": (60, 200, 110),
    "wings": (255, 200, 40),
}
ITEM_MSG = {
    "shield": "Escudo: revive 1 vez!",
    "super": "Super pulo!",
    "wings": "Voo por 5 segundos!",
}


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def bio_idx(m, loop=False):
    """Os seis primeiros biomas se repetem; o Paraíso fica fixo após 20.000 m."""
    seg = int(m // 200)
    if loop:
        i = seg % 7
        n = (i + 1) % 7
    elif m >= PARAISO_M:
        i = n = 6
    else:
        i = seg % 6
        n = 6 if (seg + 1) * 200 >= PARAISO_M else (seg + 1) % 6
    t = max(0, min(1, (m % 200 - 170) / 30))
    return i, n, t


def bio(m, loop=False):
    i, n, t = bio_idx(m, loop)
    return i, B[i], B[n], t


def tier(m):
    return min(5, int(m // 200))


# ---------- texto ----------
DARK = (21, 26, 43)


@lru_cache(maxsize=None)
def font(size):
    return pygame.font.Font(None, size)


@lru_cache(maxsize=300)
def lbl(txt, size, color):
    return font(size).render(txt, True, color)


@lru_cache(maxsize=300)
def tsurf(txt, size, w=3):
    fnt = font(size)
    base = fnt.render(txt, True, (255, 255, 255))
    ol = fnt.render(txt, True, DARK)
    surf = pygame.Surface(
        (base.get_width() + 2 * w, base.get_height() + 2 * w),
        pygame.SRCALPHA,
    )
    for dx in range(-w, w + 1):
        for dy in range(-w, w + 1):
            if dx * dx + dy * dy <= w * w + 1:
                surf.blit(ol, (dx + w, dy + w))
    surf.blit(base, (w, w))
    return surf


def text(txt, size, x, y, anchor="c", w=3, alpha=255):
    t = tsurf(txt, size, w)
    if alpha < 255:
        t.set_alpha(alpha)
    r = t.get_rect()
    if anchor == "c":
        r.midtop = (x, y)
    elif anchor == "l":
        r.topleft = (x, y)
    else:
        r.topright = (x, y)
    g.blit(t, r)
    if alpha < 255:
        t.set_alpha(255)


def plain(txt, size, x, y, color=(255, 255, 255)):
    t = lbl(txt, size, color)
    g.blit(t, t.get_rect(midtop=(x, y)))


def rr(c, x, y, w, h, r):
    pygame.draw.rect(g, c, (x, y, w, h), 0, border_radius=r)


@lru_cache(maxsize=32)
def pill_surf(w, h, alpha):
    s_ = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(
        s_,
        (14, 17, 24, alpha),
        (0, 0, w, h),
        0,
        border_radius=h // 2,
    )
    return s_.convert_alpha()


def pill(x, y, w, h, alpha=185):
    g.blit(pill_surf(w, h, alpha), (x, y))


def icon(k, cx, cy, r):
    pygame.draw.circle(g, (255, 255, 255), (cx, cy), r + 2)
    pygame.draw.circle(g, ITEM_COL[k], (cx, cy), r)
    w = (255, 255, 255)
    if k == "shield":
        pygame.draw.polygon(
            g,
            w,
            [
                (cx - r * 0.5, cy - r * 0.5),
                (cx + r * 0.5, cy - r * 0.5),
                (cx + r * 0.5, cy + r * 0.1),
                (cx, cy + r * 0.65),
                (cx - r * 0.5, cy + r * 0.1),
            ],
        )
    elif k == "super":
        for dy in (-0.45, 0.15):
            pygame.draw.polygon(
                g,
                w,
                [
                    (cx, cy + r * dy - r * 0.3),
                    (cx - r * 0.5, cy + r * dy + r * 0.3),
                    (cx + r * 0.5, cy + r * dy + r * 0.3),
                ],
            )
    else:
        pygame.draw.polygon(
            g,
            w,
            [(cx - 1, cy), (cx - r * 0.75, cy - r * 0.5), (cx - r * 0.5, cy + r * 0.35)],
        )
        pygame.draw.polygon(
            g,
            w,
            [(cx + 1, cy), (cx + r * 0.75, cy - r * 0.5), (cx + r * 0.5, cy + r * 0.35)],
        )


# ---------- botões ----------
BL, BR, BJ = (48, 554), (128, 554), (312, 554)


def make_btn(shape, on):
    s_ = pygame.Surface((68, 68), pygame.SRCALPHA)
    pygame.draw.circle(s_, (255, 255, 255, 150 if on else 76), (34, 34), 33)
    pygame.draw.circle(s_, (255, 255, 255, 190), (34, 34), 33, 2)
    pts = {
        "l": [(44, 18), (44, 50), (22, 34)],
        "r": [(24, 18), (24, 50), (46, 34)],
        "u": [(34, 20), (20, 46), (48, 46)],
    }[shape]
    pygame.draw.polygon(s_, (255, 255, 255), pts)
    return s_.convert_alpha()


BTN_IMG = {(k, o): make_btn(k, o) for k in "lru" for o in (False, True)}
touches = {}

# ---------- superfícies reaproveitadas (criadas uma única vez) ----------
BG_STEPS = 12


@lru_cache(maxsize=14)
def bg_surface(i, n, k):
    """Fundo em degradê já pronto; só muda durante a transição entre biomas."""
    tt = k / BG_STEPS
    top = mix(B[i]["t"], B[n]["t"], tt)
    bot = mix(B[i]["b"], B[n]["b"], tt)
    surf = pygame.Surface((W, H)).convert()
    for r in range(60):
        surf.fill(mix(top, bot, r / 59), (0, r * 10, W, 10))
    return surf


DIM = pygame.Surface((W, H)).convert()
DIM.fill((0, 0, 0))
DIM.set_alpha(110)
FLASH = pygame.Surface((W, H)).convert()
FLASH.fill((255, 255, 255))
SOUND_OVERLAY = pygame.Surface((W, H), pygame.SRCALPHA)
SOUND_OVERLAY.fill((12, 16, 30, 205))
SOUND_OVERLAY = SOUND_OVERLAY.convert_alpha()
SHIELD_FX = pygame.Surface((52, 52), pygame.SRCALPHA)
pygame.draw.circle(SHIELD_FX, (90, 170, 255, 70), (26, 26), 26)
pygame.draw.circle(SHIELD_FX, (160, 215, 255, 220), (26, 26), 26, 3)
SHIELD_FX = SHIELD_FX.convert_alpha()


def held(c):
    return any(
        (x - c[0]) ** 2 + (y - c[1]) ** 2 <= 42 * 42
        for x, y in touches.values()
    )


# ---------- estado ----------
s = NS(
    mode="menu",
    sound_return="menu",
    t=0,
    dm=0.0,
    m=0,
    rec=load_rec(),
    cool=0,
    cam=0,
    plats=[],
    items=[],
    p=None,
    hmax=0,
    topY=0,
    lastbi=0,
    banner=0,
    btxt="",
    flash=0,
    shake=0,
    newrec=False,
    gap=0,
    last=0,
    cnt=6,
    ttxt="",
    tt=0,
    hl=False,
    hr=False,
    hj=False,
)
BTN_RECT = {
    "menu": pygame.Rect(90, 400, 180, 56),
    "over": pygame.Rect(70, 440, 220, 56),
    "menu_sound": pygame.Rect(105, 464, 150, 48),
    "over_sound": pygame.Rect(110, 510, 140, 46),
    "sound_back": pygame.Rect(20, 24, 96, 42),
    "music_toggle": pygame.Rect(218, 140, 112, 44),
    "music_down": pygame.Rect(78, 220, 42, 42),
    "music_up": pygame.Rect(240, 220, 42, 42),
    "effects_toggle": pygame.Rect(218, 320, 112, 44),
    "effects_down": pygame.Rect(78, 400, 42, 42),
    "effects_up": pygame.Rect(240, 400, 42, 42),
}


def gen():
    while s.topY > s.cam - 120:
        m2 = (H - 40 - s.topY) / 10
        bi = tier(m2)
        s.topY -= random.uniform(56, 98 + min(30, m2 / 15))
        w = max(50, 78 - m2 / 30)
        r = random.random()
        ty = 0
        if r > 1 - TRAMP_CHANCE:
            ty = 3
        elif bi >= 1 and r < 0.22:
            ty = 1
        elif bi >= 2 and r < 0.38:
            ty = 2
        pl = NS(
            x=random.uniform(0, W - w),
            y=s.topY,
            w=w,
            type=ty,
            vx=random.choice((-1, 1)) * (0.8 + bi * 0.15),
            dead=False,
            crumble=0,
            sq=0,
        )
        s.plats.append(pl)
        s.cnt -= 1
        if s.cnt <= 0 and ty not in (2, 3):
            s.items.append(
                NS(x=pl.x + pl.w / 2, y=pl.y - 34, k=random.choice(list(ITEM_COL)))
            )
            s.cnt = random.randint(*ITEM_EVERY)


def start():
    s.p = NS(x=W / 2, y=H - 40, vx=0, vy=0, req=0, gnd=COYOTE, shield=False, sj=0, fly=0)
    s.cam = 0
    s.plats = [NS(x=0, y=H - 40, w=W, type=0, vx=0, dead=False, crumble=0, sq=0)]
    s.items = []
    s.cnt = 6
    s.hmax = 0
    s.m = 0
    s.topY = H - 40
    s.lastbi = 0
    s.banner = 150
    s.btxt = B[0]["n"]
    s.flash = 0
    s.shake = 0
    s.tt = 0
    touches.clear()
    s.hl = s.hr = s.hj = False
    s.mode = "play"
    gen()


def end():
    s.mode = "over"
    s.cool = 40
    s.last = s.m
    s.gap = s.rec - s.m
    s.newrec = s.m > s.rec
    if s.newrec:
        s.rec = s.m
        save_rec(s.rec)
    touches.clear()


def press_jump():
    if s.mode == "play":
        s.p.req = JUMP_BUFFER


def revive():
    """Escudo ativo: em vez de morrer, o jogador volta numa plataforma e é lançado para cima."""
    p = s.p
    p.shield = False
    w = 96
    q = NS(
        x=max(0, min(W - w, p.x - w / 2)),
        y=s.cam + H * 0.7,
        w=w,
        type=0,
        vx=0,
        dead=False,
        crumble=0,
        sq=0,
    )
    s.plats.append(q)
    p.x = q.x + q.w / 2
    p.y = q.y
    p.vx = 0
    p.vy = -JUMP
    p.gnd = p.req = 0
    s.flash = 0.6
    s.shake = 8
    toast("O escudo te salvou!")
    play_sfx("revive")


def toast(msg):
    s.ttxt = msg
    s.tt = 70


def update():
    s.t += 1
    if s.cool > 0:
        s.cool -= 1
    if s.mode == "menu":
        s.dm += 0.35
        return
    if s.mode != "play":
        return
    k = pygame.key.get_pressed()
    s.hl, s.hr, s.hj = held(BL), held(BR), held(BJ)
    L = k[pygame.K_LEFT] or k[pygame.K_a] or s.hl
    R = k[pygame.K_RIGHT] or k[pygame.K_d] or s.hr
    jh = k[pygame.K_UP] or k[pygame.K_w] or k[pygame.K_SPACE] or s.hj
    d = (1 if R else 0) - (1 if L else 0)
    p = s.p
    p.vx += (d * 4.6 - p.vx) * 0.22
    p.x += p.vx
    if p.x < -12:
        p.x = W + 12
    if p.x > W + 12:
        p.x = -12
    # ---- física vertical ----
    if p.fly > 0:
        p.fly -= 1
        p.vy += ((-4.8 if jh else 1.0) - p.vy) * 0.12
    elif p.vy < 0:
        p.vy += GRAV
    else:
        p.vy = min(MAX_FALL, p.vy + FALL_G)
    py = p.y
    p.y += p.vy

    # ---- plataformas: atualiza e testa o pouso na mesma passada ----
    falling = p.vy >= 0
    left, right = p.x - EDGE, p.x + EDGE
    ground = False
    for q in s.plats:
        if q.sq:
            q.sq -= 1
        if not q.dead:
            if q.type == 1:
                q.x += q.vx
                if q.x < 0 or q.x + q.w > W:
                    q.vx = -q.vx
            if q.crumble:
                q.crumble -= 1
                if q.crumble == 0:
                    q.dead = True
        if q.dead:
            q.y += 5
            continue
        if falling and py <= q.y + LAND_TOL and p.y >= q.y and left < q.x + q.w and right > q.x:
            falling = False  # só uma plataforma por frame
            p.y = q.y
            if q.type == 3:
                p.vy = -TRAMP_V
                q.sq = 12
                p.gnd = 0
                s.shake = max(s.shake, 4)
                play_sfx("trampoline")
            else:
                p.vy = 0
                ground = True
                if q.type == 1:
                    p.x += q.vx
                if q.type == 2 and not q.crumble:
                    q.crumble = 25

    # ---- pulo: um único ponto de decisão, depois da colisão ----
    # gnd = tolerância de chão (inclui "coyote time"); req = toque antecipado
    if ground:
        p.gnd = COYOTE
    elif p.gnd:
        p.gnd -= 1
    if p.gnd and not p.fly and (p.req or (HOLD_JUMP and jh)):
        if p.sj:
            p.sj -= 1
            p.vy = -SUPER_JUMP
            play_sfx("super_jump")
        else:
            p.vy = -JUMP
            play_sfx("jump")
        p.gnd = p.req = 0
    elif p.req:
        p.req -= 1

    for it in s.items[:]:
        if (p.x - it.x) ** 2 + (p.y - 14 - it.y) ** 2 < 26 * 26:
            s.items.remove(it)
            play_sfx("potion")
            if it.k == "shield":
                p.shield = True
            elif it.k == "super":
                p.sj += SUPER_CHARGES
            else:
                p.fly = FLY_FRAMES
                p.vy = min(p.vy, -4)
            toast(ITEM_MSG[it.k])
    tc = p.y - H * 0.42
    if tc < s.cam:
        s.cam += (tc - s.cam) * 0.15
    s.hmax = max(s.hmax, H - 40 - p.y)
    s.m = int(s.hmax // 10)
    gen()
    s.plats = [q for q in s.plats if q.y - s.cam < H + 80]
    s.items = [i for i in s.items if i.y - s.cam < H + 80]
    bi = bio(s.m)[0]
    if bi != s.lastbi:
        s.lastbi = bi
        s.banner = 170
        s.btxt = B[bi]["n"]
        s.flash = 0.7
        if bi == 6:
            toast("Você chegou ao Paraíso!")
    if p.y - s.cam > H + 40:
        if p.shield:
            revive()
        else:
            end()
            return
    if s.shake > 0:
        s.shake -= 1
    if s.flash > 0:
        s.flash -= 0.02
    if s.banner > 0:
        s.banner -= 1
    if s.tt > 0:
        s.tt -= 1


# ---------- desenho ----------
def draw():
    menu = s.mode == "menu"
    cur = s.dm if menu else s.m
    bi, ni, t = bio_idx(cur, menu)
    a, b = B[bi], B[ni]
    col = lambda k: mix(a[k], b[k], t)
    bot = col("b")
    g.blit(bg_surface(bi, ni, int(t * BG_STEPS)), (0, 0))
    if s.mode == "sound":
        draw_sound_menu()
        return
    if menu:
        draw_menu()
        return
    cam = s.cam
    p = s.p
    pf, gf = col("p"), col("g")
    for q in s.plats:
        sy = q.y - cam
        if sy < -20:
            continue
        qx = q.x + (random.uniform(-1.5, 1.5) if q.crumble > 0 else 0)
        if q.type == 3:
            sq = q.sq / 12 * 5
            rr(DARK, qx + q.w * 0.12, sy + 6 + sq, q.w * 0.76, 6, 2)
            rr((255, 70, 100), qx, sy + sq, q.w, 7, 3)
            rr((255, 225, 77), qx, sy + sq, q.w, 3, 2)
            continue
        pcol, gcol = pf, gf
        if q.type == 2:
            pcol = mix(pf, bot, 0.35)
            gcol = mix(gf, bot, 0.35)
        rr(pcol, qx, sy, q.w, 12, 5)
        rr(gcol, qx, sy, q.w, 5, 3)
        if q.type == 1:
            rr(DARK, qx + 4, sy + 7, q.w - 8, 3, 2)
    for it in s.items:
        sy = it.y - cam + math.sin(s.t / 12 + it.x) * 3
        if -20 < sy < H + 20:
            icon(it.k, int(it.x), int(sy), 13)
    x = p.x
    y = p.y - cam
    f = -1 if p.vx < -0.5 else 1
    if p.fly > 0:
        fl = math.sin(s.t / 3) * 8
        wc = (255, 255, 255)
        pygame.draw.polygon(g, wc, [(x - 8, y - 18), (x - 32, y - 30 + fl), (x - 22, y - 6 + fl / 2)])
        pygame.draw.polygon(g, wc, [(x + 8, y - 18), (x + 32, y - 30 + fl), (x + 22, y - 6 + fl / 2)])
    rr((59, 42, 32), x - f * 10 - 4, y - 22, 8, 13, 3)
    rr((255, 90, 54), x - 9, y - 22, 18, 16, 5)
    rr((38, 48, 77), x - 8, y - 7, 6, 7, 2)
    rr((38, 48, 77), x + 2, y - 7, 6, 7, 2)
    pygame.draw.circle(g, (255, 215, 168), (int(x), int(y - 28)), 8)
    pygame.draw.circle(g, (255, 225, 77), (int(x), int(y - 30)), 9, 0, True, True, False, False)
    pygame.draw.rect(g, (17, 17, 17), (x - 4 + f * 2, y - 28, 2, 3))
    pygame.draw.rect(g, (17, 17, 17), (x + 2 + f * 2, y - 28, 2, 3))
    if p.shield:
        g.blit(SHIELD_FX, (p.x - 26, p.y - cam - 46))
    text(f"{s.m} m", 38, 14, 12, "l", 3)
    text(f'{B[bi]["n"]}  |  Recorde {max(s.rec, s.m)} m', 20, 14, 44, "l", 2)
    hx = 14
    if p.shield:
        icon("shield", hx + 11, 83, 11)
        hx += 30
    if p.sj > 0:
        icon("super", hx + 11, 83, 11)
        text(f"x{p.sj}", 22, hx + 26, 74, "l", 2)
        hx += 56
    if p.fly > 0:
        icon("wings", hx + 11, 83, 11)
        if p.fly > 60 or (p.fly // 6) % 2:
            pygame.draw.rect(g, DARK, (hx + 28, 77, 84, 14), 0, border_radius=7)
            pygame.draw.rect(
                g,
                (255, 200, 40),
                (hx + 30, 79, int(80 * p.fly / FLY_FRAMES), 10),
                0,
                border_radius=5,
            )
    if s.tt > 0:
        text(s.ttxt, 36, W // 2, 108, "c", 3, int(255 * min(1, s.tt / 20)))
    if s.banner > 0:
        al = max(0, min(1, s.banner / 30, (170 - s.banner) / 20))
        text(s.btxt, 54, W // 2, int(H * 0.3) - 20, "c", 4, int(255 * al))
    if s.flash > 0:
        FLASH.set_alpha(int(min(0.6, s.flash) * 255))
        g.blit(FLASH, (0, 0))
    if s.mode == "play":
        for c, k, on in ((BL, "l", s.hl), (BR, "r", s.hr), (BJ, "u", s.hj)):
            g.blit(BTN_IMG[(k, on)], (c[0] - 34, c[1] - 34))
    if s.mode == "over":
        draw_over()


def draw_button(rect, label):
    pygame.draw.rect(g, (184, 134, 11), rect.move(0, 6), 0, border_radius=14)
    pygame.draw.rect(g, (255, 210, 63), rect, 0, border_radius=14)
    t_ = lbl(label, 38, DARK)
    g.blit(t_, t_.get_rect(center=rect.center))


def draw_menu():
    text("ESCALE", 120, W // 2, 130, "c", 5)
    pill(100, 300, 160, 40)
    plain(f"Recorde: {s.rec} m", 30, W // 2, 310)
    draw_button(BTN_RECT["menu"], "Começar")
    draw_button(BTN_RECT["menu_sound"], "Som")


def draw_over():
    g.blit(DIM, (0, 0))
    text("Fim da subida", 56, W // 2, 120, "c", 4)
    text(f"{s.last} m", 110, W // 2, 190, "c", 5)
    pill(60, 305, 240, 40)
    plain(
        "Novo recorde!" if s.newrec else f"Faltam {s.gap} m para o recorde",
        28,
        W // 2,
        314,
    )
    pill(100, 365, 160, 40)
    plain(f"Recorde: {s.rec} m", 28, W // 2, 374)
    draw_button(BTN_RECT["over"], "Subir de novo")
    draw_button(BTN_RECT["over_sound"], "Som")


def draw_small_button(rect, label, enabled=None):
    if enabled is None:
        color = (255, 210, 63)
        text_color = DARK
    else:
        color = (73, 190, 120) if enabled else (105, 112, 130)
        text_color = (255, 255, 255)
    pygame.draw.rect(g, (30, 35, 52), rect.move(0, 3), 0, border_radius=10)
    pygame.draw.rect(g, color, rect, 0, border_radius=10)
    label_surf = lbl(label, 26, text_color)
    g.blit(label_surf, label_surf.get_rect(center=rect.center))


def draw_volume_row(label, value, down_rect, up_rect, y):
    plain(label, 21, W // 2, y - 31)
    draw_small_button(down_rect, "-")
    draw_small_button(up_rect, "+")
    rail = pygame.Rect(132, y + 3, 96, 10)
    pygame.draw.rect(g, (70, 78, 96), rail, 0, border_radius=5)
    fill_width = int(rail.width * value)
    if fill_width > 0:
        pygame.draw.rect(
            g,
            (255, 210, 63),
            (rail.x, rail.y, fill_width, rail.height),
            0,
            border_radius=5,
        )
    plain(f"{int(value * 100)}%", 20, W // 2, y + 17)


def draw_sound_menu():
    g.blit(SOUND_OVERLAY, (0, 0))

    draw_small_button(BTN_RECT["sound_back"], "Voltar")
    text("SOM", 66, W // 2, 72, "c", 4)

    plain("Música", 26, 76, 148)
    draw_small_button(
        BTN_RECT["music_toggle"],
        "Ligada" if audio.music_enabled else "Desligada",
        audio.music_enabled,
    )
    draw_volume_row(
        "Volume da música",
        audio.music_volume,
        BTN_RECT["music_down"],
        BTN_RECT["music_up"],
        220,
    )

    plain("Efeitos sonoros", 24, 91, 328)
    draw_small_button(
        BTN_RECT["effects_toggle"],
        "Ligados" if audio.effects_enabled else "Desligados",
        audio.effects_enabled,
    )
    draw_volume_row(
        "Volume dos efeitos",
        audio.effects_volume,
        BTN_RECT["effects_down"],
        BTN_RECT["effects_up"],
        400,
    )

    if audio.available:
        plain("Inclui sons de pulo e coleta de poções.", 18, W // 2, 484)
    else:
        plain("Áudio indisponível neste dispositivo.", 18, W // 2, 484)


def present():
    global dirty
    jx = jy = 0
    if s.shake > 0 and s.mode == "play":
        jx, jy = random.randint(-4, 4), random.randint(-4, 4)
    # só limpa as bordas quando há barras pretas visíveis ou tremor de tela
    if dirty or jx or jy:
        screen.fill((14, 17, 24))
        dirty = bool(jx or jy)
    if scaled is None:
        screen.blit(g, (int(ox + jx), int(oy + jy)))
    else:
        pygame.transform.scale(g, scaled_size, scaled)
        screen.blit(scaled, (int(ox + jx), int(oy + jy)))
    pygame.display.flip()


# ---------- entrada ----------
use_touch = False
BACK_KEYS = {pygame.K_ESCAPE}
if ANDROID:
    for key_name in ("K_AC_BACK", "K_BACKSPACE"):
        key_code = getattr(pygame, key_name, None)
        if key_code is not None:
            BACK_KEYS.add(key_code)


def to_logic(px, py):
    return (px - ox) / sc, (py - oy) / sc


def down(tid, px, py):
    x, y = to_logic(px, py)
    touches[tid] = (x, y)
    if s.mode == "play":
        if (x - BJ[0]) ** 2 + (y - BJ[1]) ** 2 <= 44 * 44:
            press_jump()
    elif s.mode == "sound":
        if BTN_RECT["sound_back"].collidepoint(x, y):
            s.mode = s.sound_return
        elif BTN_RECT["music_toggle"].collidepoint(x, y):
            audio.music_enabled = not audio.music_enabled
            sync_music()
        elif BTN_RECT["music_down"].collidepoint(x, y):
            change_volume("music_volume", -0.1)
        elif BTN_RECT["music_up"].collidepoint(x, y):
            change_volume("music_volume", 0.1)
        elif BTN_RECT["effects_toggle"].collidepoint(x, y):
            audio.effects_enabled = not audio.effects_enabled
        elif BTN_RECT["effects_down"].collidepoint(x, y):
            change_volume("effects_volume", -0.1)
        elif BTN_RECT["effects_up"].collidepoint(x, y):
            change_volume("effects_volume", 0.1)
    elif s.mode == "menu":
        if BTN_RECT["menu_sound"].collidepoint(x, y):
            s.sound_return = "menu"
            s.mode = "sound"
        elif s.cool <= 0 and BTN_RECT["menu"].collidepoint(x, y):
            start()
    elif s.mode == "over":
        if BTN_RECT["over_sound"].collidepoint(x, y):
            s.sound_return = "over"
            s.mode = "sound"
        elif s.cool <= 0 and BTN_RECT["over"].collidepoint(x, y):
            start()


def in_jump(x, y):
    return (x - BJ[0]) ** 2 + (y - BJ[1]) ** 2 <= 44 * 44


def move(tid, px, py):
    if tid in touches:
        old = touches[tid]
        new = to_logic(px, py)
        touches[tid] = new
        # deslizar o dedo para dentro do botão de pulo também pula
        if s.mode == "play" and in_jump(*new) and not in_jump(*old):
            press_jump()


running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False
        elif e.type == pygame.VIDEORESIZE:
            layout()
        elif e.type == pygame.FINGERDOWN:
            use_touch = True
            down(e.finger_id, e.x * sw, e.y * sh)
        elif e.type == pygame.FINGERMOTION:
            move(e.finger_id, e.x * sw, e.y * sh)
        elif e.type == pygame.FINGERUP:
            touches.pop(e.finger_id, None)
        elif e.type == pygame.MOUSEBUTTONDOWN and not use_touch:
            down("m", *e.pos)
        elif e.type == pygame.MOUSEMOTION and not use_touch:
            move("m", *e.pos)
        elif e.type == pygame.MOUSEBUTTONUP and not use_touch:
            touches.pop("m", None)
        elif e.type == pygame.KEYDOWN:
            if e.key in BACK_KEYS:
                if s.mode == "sound":
                    s.mode = s.sound_return
                else:
                    running = False
            elif e.key in (pygame.K_SPACE, pygame.K_RETURN) and s.mode in ("menu", "over") and s.cool <= 0:
                start()
            elif e.key in (pygame.K_SPACE, pygame.K_UP, pygame.K_w) and s.mode == "play":
                press_jump()
    if running:
        update()
        draw()
        present()
        clock.tick(60)

pygame.quit()
sys.exit()
