"""AP patch container for Mega Man X6 (PS1, NTSC-U, SLUS-01395).

Follows the X5 world's shape, which itself improved on the MMX4 apworld: no
external xdelta executable and no separate basepatch file. The edit list is
tiny and lives in disc.py, so the vanilla image is patched in pure Python -
including the MANDATORY per-sector EDC/ECC regeneration, without which emulator
disc layers error-correct the edits back to vanilla and the patch silently does
nothing.

Any per-seed data would ride inside the .apmmx6 as JSON rather than as
APTokenMixin tokens, because raw token pokes would bypass parity regeneration.
v0.1 has none: the A1 patch is identical for every seed.
"""
import hashlib
import json
import logging
import os
from typing import TYPE_CHECKING

import settings
import Utils
from worlds.Files import APPatchExtension, APProcedurePatch

from . import damage, disc, palettes

if TYPE_CHECKING:
    from . import MMX6World

logger = logging.getLogger()

# MD5s of the raw 2352-byte NTSC-U images this patch is built and tested
# against. BOTH are verified, 2026-08-25, by actually patching them.
#
# Redump "Mega Man X6 (USA) (Rev 1)" is the canonical dump and what players
# will almost always have. The development image is that same disc plus eight
# trailing ZERO sectors, with the only other differences confined to ISO
# filesystem metadata (sectors 16, 22-24) and a handful of data sectors around
# 222000 - none of which any patch touches.
#
# What matters, and what was measured rather than assumed: SLUS_013.95 and
# ROCK_X6.BIN are **byte-identical between the two images**, 0 differing
# sectors across both containers. So every disc offset derived on one is valid
# on the other, and patching the Redump image produces exactly the same three
# sectors with valid EDC/ECC. verify_release.py re-proves this on every run.
HASH_US_REDUMP = "237b6feddd1a88e86ab1cddc8822f03f"   # (USA) (Rev 1), canonical
HASH_US_DEV = "ae1f630f686edb48f84f8d69346bc8a8"      # Redump + 8 zero sectors
ACCEPTED_HASHES = {HASH_US_REDUMP, HASH_US_DEV}
HASH_US = HASH_US_REDUMP    # kept for callers importing the old name


class MMX6Settings(settings.Group):
    class RomFile(settings.UserFilePath):
        description = "Mega Man X6 (USA) disc image"
        copy_to = "Megaman X6.bin"
        md5s = sorted(ACCEPTED_HASHES)


def get_base_rom_path() -> str:
    from . import MMX6World
    path = MMX6World.settings.rom_file
    if not os.path.exists(path):
        path = Utils.user_path(path)
    return path


def diagnose_rejected_image(data: bytes) -> str | None:
    """Say something useful about an image that failed the hash check.

    A bare "MD5 mismatch" is unhelpful in the case that actually happens most:
    the player pointed the base-image setting at a disc a PREVIOUS seed
    produced. On X5 that exact confusion sent a tester deleting every X5 file
    he had, so the rejection there learned to name the cause. Same here.

    Returns a sentence to append to the rejection, or None when nothing more
    specific than "wrong file" can be said.
    """
    # A1's static-EXE site. Always patched on any disc this world produced,
    # regardless of which QoL options the seed used, so one site is enough.
    # This is the same byte the CLIENT probes in RAM.
    site = disc.addr_to_disc(0x8003C278, disc.REGION_EXE)
    vanilla, patched = bytes.fromhex("6000a290"), bytes.fromhex("ab00a290")
    if len(data) < site + len(patched):
        return ("The file is too small to be a Mega Man X6 disc image at all - "
                "check it is the raw 2352-byte .bin and not a .cue, .iso, .ecm "
                "or an archive.")
    here = data[site:site + len(patched)]
    if here == patched:
        return ("That file is a disc THIS WORLD ALREADY PATCHED, from an "
                "earlier seed. Point the `mmx6_options` base-image setting at "
                "your original unpatched disc instead - patching a patched "
                "disc is never what you want, and the patched one stays valid "
                "for the seed it belongs to.")
    if here == vanilla:
        return ("The bytes this world patches are intact, so this looks like a "
                "Mega Man X6 disc - just not a dump we have tested. Expected "
                "the Redump 'Mega Man X6 (USA) (Rev 1)' rip.")
    return None


def get_base_rom_bytes() -> bytes:
    path = get_base_rom_path()
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.md5(data).hexdigest()
    if digest not in ACCEPTED_HASHES:
        message = (
            f"Mega Man X6: supplied disc image has MD5 {digest}, which this "
            f"world has not been tested against. Expected the Redump "
            f"'Mega Man X6 (USA) (Rev 1)' dump, {HASH_US_REDUMP} (raw "
            f"2352-byte .bin).")
        detail = diagnose_rejected_image(data)
        if detail:
            message += chr(10) + chr(10) + detail
        raise ValueError(message)
    return data


class MMX6PatchExtension(APPatchExtension):
    game = "Mega Man X6"

    @staticmethod
    def apply_basepatch(caller: APProcedurePatch, rom: bytes) -> bytes:
        extra: list[tuple] = []
        try:
            seed_edits = json.loads(
                caller.get_file("seed_edits.json").decode("utf-8"))
            for entry in seed_edits:
                # `van` rides along so the QoL edits are verified against the
                # image with the same rigour as A1 - a patch file built for a
                # different dump must fail loudly, not corrupt code quietly.
                van = entry.get("van")
                extra.append((entry["addr"], bytes.fromhex(entry["hex"]),
                              entry["region"],
                              bytes.fromhex(van) if van else None))
        except KeyError:
            pass    # no per-seed edits in this patch
        return disc.apply_basepatch(rom, extra)

    @staticmethod
    def apply_palettes(caller: APProcedurePatch, rom: bytes) -> bytes:
        """Cosmetic recolour: the seed's own choice, or a host.yaml override.

        The colour normally comes from the player's YAML and rides inside the
        patch, so it shows on the website generator, is validated at
        generation rather than failing quietly here, and lands in the spoiler.
        host.yaml remains as an override, which is what still allows a colour
        to be changed without a new seed.

        Runs after apply_basepatch; the two never touch the same sectors - the
        palettes are in ROCK_X6.DAT, far from the code the basepatch edits.
        """
        import random

        # The seed's own choice. GUARDED rather than required: a patch built
        # before these were YAML options carries no such file, and must still
        # open - for those, host.yaml is the only source, exactly as before.
        seed_choice: dict = {}
        try:
            seed_choice = json.loads(
                caller.get_file("palettes.json").decode("utf-8"))
        except Exception:
            pass

        # settings.get_settings() memoises on the function object, so a player
        # who patches, edits host.yaml and patches again WITHOUT restarting the
        # Launcher would silently get their previous colours. Re-read from disk
        # for this lookup, then hand the old cache back. (Found on X5 by testing
        # the re-patch workflow rather than assuming it.)
        cached = getattr(settings.get_settings, "_cache", None)
        try:
            settings.get_settings._cache = None
            group = settings.get_settings().mmx6_options
        except Exception:
            group = None
        finally:
            settings.get_settings._cache = cached

        host_values = {
            target: (getattr(group, f"{target}_palette", palettes.UNSET)
                     if group is not None else palettes.UNSET)
            for target in palettes.TARGETS
        }
        choices = palettes.choose(seed_choice, host_values)
        for target, value in choices.items():
            if palettes.overrides(host_values.get(target)):
                logger.info("MMX6 palette %s: %s, overridden from host.yaml",
                            target, value)

        if all((c or palettes.VANILLA).strip().lower() == palettes.VANILLA
               for c in choices.values()):
            return rom

        rng = random.Random(getattr(caller, "player_name", "") or None)
        image = bytearray(rom)
        touched = palettes.apply(image, choices, rng)
        for sector in sorted(touched):
            disc.regenerate_sector(image, sector)
        return bytes(image)


class MMX6ProcedurePatch(APProcedurePatch):
    hash = sorted(ACCEPTED_HASHES)
    game = "Mega Man X6"
    patch_file_ending = ".apmmx6"
    result_file_ending = ".cue"
    procedure = [
        ("apply_basepatch", []),
        ("apply_palettes", []),
    ]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_bytes()

    def patch(self, target: str) -> None:
        file_name = target[:-4]
        if os.path.exists(file_name + ".bin") and os.path.exists(file_name + ".cue"):
            logger.info("Patched disc + CUE already exist!")
            return

        super().patch(target)
        os.rename(target, file_name + ".bin")

        rom_name = os.path.basename(file_name)
        with open(file_name + ".cue", "w", newline="\n") as f:
            f.write(f'FILE "{rom_name}.bin" BINARY\n'
                    f'  TRACK 01 MODE2/2352\n'
                    f'    INDEX 01 00:00:00\n')


# YAML option -> the QOL_EDITS group it turns on. Kept next to the writer so
# an option added without a disc edit, or the reverse, is obvious.
QOL_OPTIONS = {
    "text_skip": "text_skip",
    "skip_intro_videos": "skip_intro_videos",
    "exit_stage_anytime": "exit_stage_anytime",
    "protect_reploids": "protect_reploids",
}


def nightmare_groups(options) -> list[str]:
    """The Nightmare-effect edit groups this seed asks for.

    Separate from QOL_OPTIONS because this one option selects any subset of
    eight groups rather than mapping one-to-one onto a single group. Sorted
    into the table's own order so two seeds with the same set produce the same
    edit list, whatever order the YAML listed them in.
    """
    wanted = options.disabled_nightmare_effects.effects
    return [disc.nightmare_group_name(e) for e in disc.NIGHTMARE_EFFECTS
            if e in wanted]


def qol_features(options) -> list[str]:
    """The QoL edit groups this seed's options ask for, in a stable order."""
    return [group for option, group in QOL_OPTIONS.items()
            if getattr(options, option).value] + nightmare_groups(options)


def patch_rom(world: "MMX6World", patch: MMX6ProcedurePatch) -> None:
    """Attach per-seed data.

    A1 is seed-independent and lives in disc.BASE_EDITS. The QoL options are
    not: each one is a set of disc edits the player either asked for or did
    not, so they ride in the .apmmx6 as an explicit edit list. Everything else
    the seed decides is carried by slot_data and applied by the client.
    """
    seed_edits = list(disc.qol_edits(qol_features(world.options)))

    # Issue -1: under `all_mavericks` the endgame must open on the eighth
    # Maverick and on nothing else. Vanilla also opens it on 3000 Nightmare
    # Souls or the High Max route, and the client cannot win that argument -
    # it writes the byte shut and the game writes it open again on the next
    # hub transition, which is the cutscene loop testers reported. Switched
    # off on the disc instead, where the decision is actually made.
    #
    # NOT applied under the `sigma` goal: there, opening on souls is the
    # game's own design and the seed is finishable either way.
    if world.options.goal == world.options.goal.option_all_mavericks:
        seed_edits += disc.ENDGAME_GATE_EDITS

    # The new-game initialiser writes 32 into both characters' life bytes.
    # The client cannot lower that - it only ever sees the save after the game
    # has written it - so a starting life other than vanilla is a disc edit.
    # Raising it could have stayed client-side, but one mechanism is simpler
    # to reason about than two, and it means a fresh save is right from the
    # first frame rather than after the first client poll.
    seed_edits += disc.starting_life_edits(world.options.starting_hp.value)

    if world.options.boss_hp_randomization:
        # Rolled here rather than in generate_early because nothing outside
        # the disc image needs to know: no logic depends on boss health, and
        # the client never reads it.
        rolls = {boss: world.random.randint(disc.BOSS_HP_MIN, disc.BOSS_HP_MAX)
                 for boss in disc.rollable_bosses()}
        seed_edits += disc.boss_hp_edits(rolls)

    if world.options.weapon_damage:
        band = damage.SCALE_BANDS[
            world.options.weapon_damage.current_key]
        low, high = band
        scales = {group: world.random.uniform(low, high)
                  for group in damage.WEAPON_GROUPS}
        seed_edits += damage.damage_edits(scales)

    edits = [{"addr": where, "region": region,
              "hex": patched.hex(), "van": van.hex()}
             for _label, where, region, van, patched in seed_edits]
    patch.write_file("seed_edits.json", json.dumps(edits).encode("utf-8"))

    # Cosmetic colours. Resolved HERE, at generation, so `random` is rolled
    # once and recorded rather than re-rolled from the player's name every
    # time the patch is opened. host.yaml can still override any of these when
    # the patch is opened - see MMX6PatchExtension.apply_palettes.
    patch.write_file("palettes.json", json.dumps({
        target: palettes.resolve(
            getattr(world.options, f"{target}_palette").current_key,
            world.random)
        for target in palettes.TARGETS
    }).encode("utf-8"))
