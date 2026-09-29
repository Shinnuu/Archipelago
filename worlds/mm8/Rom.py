"""AP patch container for Mega Man 8 (PS1, NTSC-U, SLUS-00453).

The X5/X6 shape - no external xdelta, no basepatch file, the image patched in
pure Python with per-sector EDC/ECC regeneration - adapted to a THREE-track
disc. The base "ROM" is Track 1, the only track ever edited; Tracks 2 and 3
are found beside it by size and md5, and the result is one merged .bin with a
single-FILE cue (disc.merged_cue explains why that layout is exact).

Per-seed data rides in the .apmm8 as JSON: what each Lab entry holds, turned
into text edits at patch time, when the vanilla bytes are to hand; and the
options' disc edits (seed_edits.json), rolled at generation and written
whole, each carrying the vanilla bytes it expects.
"""
import hashlib
import json
import logging
import os
import shutil
from typing import TYPE_CHECKING

import settings
import Utils
from worlds.Files import APPatchExtension, APProcedurePatch

from . import damage, disc, music, palettes, pickups

if TYPE_CHECKING:
    from . import MM8World

logger = logging.getLogger()

HASH_TRACK1 = disc.TRACK_MD5[0]
# What a patch file can ask of the apworld that applies it, beyond the code
# layout. 1: 0.1.0. 2: 0.2.0 - stage_order's seed edits, which need this
# client's lock on Duo's select slot. Stored inside seed.json's "layout",
# which 0.1.0 compares whole, so 0.1.0 refuses a format-2 patch (review m3).
PATCH_FORMAT = 2


class MM8Settings(settings.Group):
    class RomFile(settings.UserFilePath):
        """File path of Track 1 of the Mega Man 8 (USA) disc image - the
        "(Track 1).bin". Tracks 2 and 3 must be in the same folder."""
        description = "Mega Man 8 (USA) (Track 1).bin"
        md5s = [HASH_TRACK1]
        # NO copy_to: copying would take Track 1 away from the two audio
        # tracks it has to be patched together with. The setting links to the
        # player's dump where it is.

    rom_file: RomFile = RomFile("Mega Man 8 (USA) (Track 1).bin")

    # Mega Man's colour. The colour itself is an ordinary YAML option; this is
    # an OVERRIDE, so it can change without a new seed. Only a real colour (or
    # "random") overrides - "vanilla" here does nothing, because Archipelago
    # writes every default into host.yaml (palettes.overrides; X5's rule).
    mega_man_palette: str = palettes.UNSET


def get_base_rom_path() -> str:
    from . import MM8World
    path = MM8World.settings.rom_file
    if not os.path.exists(path):
        path = Utils.user_path(path)
    return path


def get_base_rom_bytes() -> bytes:
    path = get_base_rom_path()
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.md5(data).hexdigest()
    if digest != HASH_TRACK1:
        raise ValueError(
            f"Mega Man 8: {os.path.basename(path)} has MD5 {digest}. Expected "
            f"Track 1 of the Redump 'Mega Man 8 (USA)' dump, {HASH_TRACK1} - "
            f"the '(Track 1).bin', not the .cue or another track.")
    return data


class MM8PatchExtension(APPatchExtension):
    game = "Mega Man 8"

    @staticmethod
    def apply_basepatch(caller: APProcedurePatch, rom: bytes) -> bytes:
        entries = {int(part): tuple(entry) for part, entry
                   in json.loads(caller.get_file("lab.json").decode("utf-8")).items()}
        seed = json.loads(caller.get_file("seed.json").decode("utf-8"))
        # A patch without a layout predates this check; none left this machine.
        # The layout carries the patch format too (PATCH_FORMAT): 0.1.0
        # compares the whole dict, so it refuses a newer patch instead of
        # half-applying it (review m3); this apworld refuses a newer format.
        layout = dict(seed.get("layout", disc.code_layout()))
        patch_format = layout.pop("format", 1)
        if layout != disc.code_layout() or patch_format > PATCH_FORMAT:
            raise ValueError(
                "Mega Man 8: this .apmm8 was made by a different version of the Mega Man 8 "
                "apworld than the one installed, and the two lay out the disc's added code "
                "differently. Patch it with the apworld version the seed was generated with.")
        try:
            options = decode_edits(caller.get_file("seed_edits.json"))
        except KeyError:
            options = []       # a patch from before the options existed
        # What each of the player's own parts does, in its Lab entry - built
        # here at patch time, so a seed from an older apworld gets it too.
        # Exit's line depends on exit_stage_anytime, read off the seed's edits
        # by the one it always carries (an address and payload, not a label -
        # labels are frozen inside old patch files).
        from . import names
        effects = names.part_effects(any((where, payload) == disc.EXIT_ANYTIME_MARK
                                         for _label, where, _region, _vanilla, payload in options))
        edits = (list(disc.BASE_EDITS) + disc.routine_edits(rom)
                 + disc.lab_text_edits(rom, entries, effects) + disc.ap_block_edits(seed["stamp"])
                 + options)
        return disc.apply_edits(rom, edits)

    @staticmethod
    def apply_palettes(caller: APProcedurePatch, rom: bytes) -> bytes:
        """Mega Man's colour: the seed's choice, or a host.yaml override (X5's
        apply_palettes). Runs after apply_basepatch; the records are found by
        content, and the basepatch never touches their bytes."""
        import random

        seed_choice: dict = {}
        try:
            seed_choice = json.loads(caller.get_file("palettes.json").decode("utf-8"))
        except KeyError:
            pass                  # a patch from before the option
        # get_settings() memoises; re-read host.yaml so an edit between two
        # patches in one Launcher session is seen (X5), then restore the cache.
        cached = getattr(settings.get_settings, "_cache", None)
        try:
            settings.get_settings._cache = None
            group = settings.get_settings().mm8_options
        except Exception:
            group = None
        finally:
            settings.get_settings._cache = cached
        host_values = {target: (getattr(group, f"{target}_palette", palettes.UNSET)
                                if group is not None else palettes.UNSET)
                       for target in palettes.TARGETS}
        choices = palettes.choose(seed_choice, host_values)
        for target, value in choices.items():
            if palettes.overrides(host_values.get(target)):
                logger.info("Mega Man 8 palette %s: %s, overridden from host.yaml", target, value)
        if all((c or palettes.VANILLA).strip().lower() == palettes.VANILLA for c in choices.values()):
            return rom
        # Seeded on the player name, so re-patching reproduces a host.yaml "random".
        rng = random.Random(getattr(caller, "player_name", "") or None)
        image = bytearray(rom)
        for sector in sorted(palettes.apply(image, choices, rng)):
            disc.regenerate_sector(image, sector)
        return bytes(image)

    @staticmethod
    def apply_music(caller: APProcedurePatch, rom: bytes) -> bytes:
        """stage_music: rebuild the stage sound banks for the seed's deal and
        re-lay the SOUND region (music.apply_music, which re-parities what it
        touches and refuses a region that is not vanilla)."""
        try:
            assignment = json.loads(caller.get_file("music.json").decode("utf-8"))
        except KeyError:
            assignment = None     # a patch from before the option
        if not assignment:
            return rom
        image = bytearray(rom)
        music.apply_music(image, assignment)
        return bytes(image)


class MM8ProcedurePatch(APProcedurePatch):
    hash = [HASH_TRACK1]
    game = "Mega Man 8"
    patch_file_ending = ".apmm8"
    result_file_ending = ".cue"
    procedure = [("apply_basepatch", []), ("apply_palettes", []), ("apply_music", [])]

    @classmethod
    def get_source_data(cls) -> bytes:
        return get_base_rom_bytes()

    def patch(self, target: str) -> None:
        """Write "<name>.bin" (patched Track 1 + Tracks 2 and 3) and
        "<name>.cue" - or leave them alone when they already are exactly the
        disc this patch makes.

        Opening a patch always ends with the disc THIS apworld and THIS
        host.yaml make (Ivor, 2026-09-29: "as idiot proof as possible"). The
        disc is built in memory every time and compared with the one on file:
        identical, it is left untouched (so an EmuHawk that has it open is no
        problem); different in any way - made by an older apworld, a colour
        changed in host.yaml since, a damaged or half-copied file - it is
        rewritten. 0.1.0 reused any disc whose AP header matched, which an
        apworld update does not change, so a tester re-opening a 0.1.0 seed
        on 0.2.0 kept the old disc and its NO/CANCEL Lab prices (0.2.0 review
        M1). The .bin is assembled under a temporary name and only renamed
        into place once complete, so an interrupted patch never leaves a
        half-disc."""
        # Read first, always: Patch.create_rom_file hands the client the
        # server and slot from here.
        self.read()
        file_name = target[:-len(self.result_file_ending)]
        bin_path, cue_path = file_name + ".bin", file_name + ".cue"
        track1 = self._build_track1()
        track2, track3 = disc.find_audio_tracks(get_base_rom_path())
        cue = disc.merged_cue(os.path.basename(bin_path))
        if self._on_file(bin_path, cue_path, cue, track1, (track2, track3)):
            logger.info("Mega Man 8: the patched disc is already up to date: %s", bin_path)
            return
        partial = bin_path + ".partial"
        try:
            with open(partial, "wb") as out:
                out.write(track1)
                for path in (track2, track3):
                    with open(path, "rb") as f:
                        shutil.copyfileobj(f, out, 1 << 20)
            _replace(partial, bin_path)
            # UTF-8, named explicitly: the file name carries the player's name,
            # and the platform default (cp1252 here) turned "ö" into a byte no
            # UTF-8 reader resolves and crashed outright on Japanese (review
            # M2). Via a temporary name, so a failure can never leave a cue.
            with open(cue_path + ".partial", "w", encoding="utf-8", newline="\n") as f:
                f.write(cue)
            _replace(cue_path + ".partial", cue_path)
        finally:
            for leftover in (partial, cue_path + ".partial"):
                if os.path.exists(leftover):
                    os.remove(leftover)

    def _build_track1(self) -> bytes:
        """The patched Track 1, in memory: the patch's procedure, run the way
        APProcedurePatch.patch runs it (every step is ours)."""
        data = self.get_source_data_with_cache()
        for step, args in self.procedure:
            extension = getattr(MM8PatchExtension, step, None)
            if extension is None:
                raise NotImplementedError(f"Unknown procedure {step} for {self.game}.")
            data = extension(self, data, *args)
        return data

    @staticmethod
    def _on_file(bin_path: str, cue_path: str, cue: str, track1: bytes,
                 audio: tuple[str, str]) -> bool:
        """Whether `bin_path` + `cue_path` already hold exactly this disc,
        every byte compared."""
        try:
            with open(cue_path, encoding="utf-8") as f:
                if f.read() != cue:
                    return False
            expected = len(track1) + sum(os.path.getsize(path) for path in audio)
            if os.path.getsize(bin_path) != expected:
                return False
            chunk = 1 << 20
            with open(bin_path, "rb") as f:
                view = memoryview(track1)
                for at in range(0, len(track1), chunk):
                    piece = view[at:at + chunk]
                    if f.read(len(piece)) != piece:
                        return False
                for path in audio:
                    with open(path, "rb") as track:
                        while block := track.read(chunk):
                            if f.read(len(block)) != block:
                                return False
        except (OSError, UnicodeDecodeError):
            return False
        return True


def _replace(source: str, destination: str) -> None:
    """os.replace, with the one failure a player can cause and fix named: the
    old disc open in BizHawk (Windows will not replace a file in use)."""
    try:
        os.replace(source, destination)
    except PermissionError as error:
        raise PermissionError(
            f"Mega Man 8: {os.path.basename(destination)} has to be rebuilt (it is not the disc this "
            f"patch makes - an older apworld's, or one with a colour since changed), but another "
            f"program has it open. Close BizHawk, then open the .apmm8 again.") from error


def lab_entries(world: "MM8World") -> dict[int, tuple[str, str | None, str | None]]:
    """{part id: (item name, owner or None when it is this player's, game)}
    for every Lab entry, from the filled multiworld."""
    from . import names
    entries = {}
    for part in names.PARTS:
        item = world.get_location(names.shop_location(part)).item
        if item.player == world.player:
            entries[names.PART_ID[part]] = (item.name, None, None)
        else:
            entries[names.PART_ID[part]] = (item.name, world.multiworld.player_name[item.player],
                                            item.game)
    return entries


QOL_OPTIONS = ("text_skip", "skip_intro_videos", "exit_stage_anytime")


def seed_edits(world: "MM8World") -> list[tuple[str, int, str, bytes, bytes]]:
    """This seed's option-driven disc edits. Rolled values come from the
    world (generate_early), so the patch writes exactly what the spoiler
    shows. An option that is off contributes nothing, so its code stays
    vanilla on the disc."""
    edits = disc.qol_edits(name for name in QOL_OPTIONS if getattr(world.options, name))
    if world.options.weapon_damage:
        edits += damage.weapon_damage_edits(world.weapon_damage_tables)
    if world.options.boss_hp_randomization:
        edits += damage.boss_hp_edits(world.boss_hp_factors)
    if world.options.boss_damage:
        edits += damage.boss_damage_edits(world.boss_damage_factors)
    if world.options.pickupsanity:
        edits += disc.pickup_edits(pickups.KEYS)
    edits += disc.max_life_edits(int(world.options.max_life))     # none at 40
    edits += disc.stage_order_edits(int(world.options.stage_order))     # none for vanilla
    return edits


def encode_edits(edits: list[tuple[str, int, str, bytes, bytes]]) -> bytes:
    return json.dumps([[label, where, region, vanilla.hex(), payload.hex()]
                       for label, where, region, vanilla, payload in edits]).encode("utf-8")


def decode_edits(raw: bytes) -> list[tuple[str, int, str, bytes, bytes]]:
    """The inverse of encode_edits. Every edit still carries its vanilla
    bytes, so apply_edits refuses a disc they do not match."""
    return [(label, where, region, bytes.fromhex(vanilla), bytes.fromhex(payload))
            for label, where, region, vanilla, payload in json.loads(raw.decode("utf-8"))]


def write_patch(world: "MM8World", output_directory: str) -> str:
    patch = MM8ProcedurePatch(player=world.player,
                              player_name=world.multiworld.player_name[world.player])
    patch.write_file("lab.json", json.dumps(lab_entries(world)).encode("utf-8"))
    patch.write_file("seed.json", json.dumps({"stamp": world.seed_stamp(),
                                              "layout": {**disc.code_layout(), "format": PATCH_FORMAT}})
                     .encode("utf-8"))
    patch.write_file("seed_edits.json", encode_edits(seed_edits(world)))
    # Resolved HERE so `random` is rolled once, at generation, and recorded.
    patch.write_file("palettes.json", json.dumps({
        target: palettes.resolve(getattr(world.options, f"{target}_palette").current_key, world.random)
        for target in palettes.TARGETS}).encode("utf-8"))
    patch.write_file("music.json", json.dumps(world.stage_music).encode("utf-8"))
    path = os.path.join(output_directory,
                        f"{world.multiworld.get_out_file_name_base(world.player)}"
                        f"{patch.patch_file_ending}")
    patch.write(path)
    return path
