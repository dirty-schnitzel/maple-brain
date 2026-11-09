"""brain-v2 reflexes, first every tick: HP / MP potions (varied cooldowns), the HP stop, and which attack key to use
(the plain attack when MP can't pay for the skill and there are no MP potions - the user's default: potions are
expensive).
v3 layer: reflexes (every tick, first, may override). Step 1: `step` still reads the raw Obs (it runs before the
world model updates: safety first); `attack_key` reads our Character's HUD numbers (or anything with mp_now /
mp_potions)."""


class Reflexes:
    def __init__(self, cfg, hz, stats, say):
        self.cfg, self.hz, self.stats, self.say = cfg, hz, stats, say
        self.potion_t = {"hp": 0.0, "mp": 0.0}

    def step(self, now, obs, driver) -> str | None:
        """Drink when needed; returns a stop reason (HP low, no potions) or None."""
        c, k = self.cfg.safety, self.cfg.keys
        if obs.hp_now is not None and obs.hp < c.hp_stop and not obs.hp_potions:
            return f"HP {obs.hp:.0%} and no HP potions"
        for kind, share, at, have, key in (("hp", obs.hp, c.hp_potion_at, obs.hp_potions, k.hp_potion),
                                           ("mp", obs.mp, c.mp_potion_at, obs.mp_potions, k.mp_potion)):
            known = (obs.hp_now if kind == "hp" else obs.mp_now) is not None
            if known and share < at and have and now >= self.potion_t[kind]:
                driver.tap(key, self.hz.between(0.06, 0.12))
                self.potion_t[kind] = now + self.hz.between(1.5, 3.0)
                self.stats[f"{kind}_potions"] += 1
                self.say(f"{kind.upper()} {share:.0%} -> {kind.upper()} potion ({key})")
        return None

    def attack_key(self, me) -> str:
        if me.mp_now is not None and me.mp_now < self.cfg.combat.skill_mp and not me.mp_potions:
            return self.cfg.keys.basic_attack
        return self.cfg.keys.attack
