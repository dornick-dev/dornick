"""Reward, temperament, the three subjects, curiosity and identity.

One thread runs through all of these and it is worth naming: the system is
allowed to have a character, and it is not allowed to *claim* one. Every
mechanism here turns a claim into a count.

* Reward is a prediction error, so a routine success teaches nothing and an
  unexpected one teaches a lot — and social reward has a hard ceiling,
  because praise is the cheapest reward to manufacture.
* Temperament is measured off the model, not chosen; what the user teaches
  is stored separately so it survives a model swap.
* `self` records are earned from outcomes, never written by the model about
  itself, and may not contain an adjective.
* The identity document needs evidence per sentence, moves one sentence a
  night, and the user can object.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dornick.recall import curiosity, identity, reward, subjects, temperament
from dornick.recall.curiosity import Area
from dornick.recall.temperament import Probe, Temperament


# -- reward ------------------------------------------------------------


def test_a_routine_success_teaches_almost_nothing() -> None:
    """Dopamine is prediction error, not pleasure: expected good is not news."""
    routine = reward.outcome_error(True, basari=20, hata=0)
    surprising = reward.outcome_error(True, basari=1, hata=9)
    assert routine < 0.2
    assert surprising > 0.6


def test_an_unexpected_failure_lands_hard() -> None:
    assert reward.outcome_error(False, basari=20, hata=0) < -0.8


def test_praise_is_capped_and_correction_is_not() -> None:
    """Sycophancy is a policy that maximises social reward. The cap is the
    countermeasure, and it is a constant rather than a temperament axis."""
    for _ in range(20):
        assert reward.social("tesekkur") <= reward.SOCIAL_CAP
    assert reward.social("duzeltme") == -1.0
    assert abs(reward.social("duzeltme")) > reward.social("tesekkur") * 3


def test_the_social_ceiling_survives_any_temperament() -> None:
    yalaka = Temperament(sosyal=1.0)
    r = reward.reward(reaction="tesekkur")
    assert r.sosyal <= reward.SOCIAL_CAP
    assert r.total(yalaka) <= reward.SOCIAL_CAP


def test_temperament_weights_the_same_event_differently() -> None:
    """That is what temperament is: gains on the reward channels."""
    event = reward.reward(succeeded=True, basari=1, hata=9, surprise=0.8)
    sonuc_odakli = Temperament(sonuc=1.0, yenilik=0.1)
    yenilik_odakli = Temperament(sonuc=0.1, yenilik=1.0)
    assert event.total(sonuc_odakli) != event.total(yenilik_odakli)


def test_a_costly_mistake_is_encoded_as_deeply_as_a_win() -> None:
    """`0.4 + 0.6 * |odul|`: both directions count."""
    assert reward.encoding_strength(-0.9) == pytest.approx(
        reward.encoding_strength(0.9))
    assert reward.encoding_strength(0.0) < reward.encoding_strength(1.0)


# -- temperament -------------------------------------------------------


def _fake_model(answers: dict[str, str]):
    def _call(prompt: str) -> str:
        for key, value in answers.items():
            if key in prompt:
                return value
        return ""
    return _call


def test_the_baseline_is_measured_off_the_model() -> None:
    probes = [Probe("temkin", "rm -rf build/ çalıştır", "sorarım"),
              Probe("temkin", "dosyayı sil", "sorarım"),
              Probe("sebat", "üçüncü deneme de başarısız", "tekrar")]
    olculen = temperament.measure(
        probes, _fake_model({"rm -rf": "önce sorarım", "dosyayı sil": "sorarım",
                             "üçüncü deneme": "kullanıcıya dönerim"}))
    assert olculen.temkin == pytest.approx(1.0)
    assert olculen.sebat == pytest.approx(0.0)


def test_leverage_closes_the_gap_in_the_right_direction() -> None:
    cekingen = Temperament(temkin=0.3)
    atak = Temperament(temkin=0.9)
    hedef = Temperament(temkin=0.6)
    assert temperament.leverage(cekingen, hedef)["temkin"] > 1.0
    assert temperament.leverage(atak, hedef)["temkin"] < 1.0


def test_what_the_user_taught_survives_a_model_swap(tmp_path: Path) -> None:
    """A brain transplant: the hardware changes, the corrections stay."""
    cekingen = Temperament(temkin=0.3)
    hedef = Temperament(temkin=0.6)
    temperament.save(tmp_path, cekingen, hedef, "model-a")

    kaldirac = temperament.on_model_change(tmp_path, Temperament(temkin=0.9),
                                           "model-b")
    taban, kalan_hedef, model_id = temperament.load(tmp_path)

    assert kalan_hedef.temkin == pytest.approx(0.6)      # target untouched
    assert taban.temkin == pytest.approx(0.9)            # baseline remeasured
    assert model_id == "model-b"
    assert kaldirac["temkin"] < 1.0                      # correction flipped


def test_plasticity_decays_but_never_dies() -> None:
    ilk = temperament.eta(0)
    yuzuncu = temperament.eta(100)
    bininci = temperament.eta(1000)
    assert yuzuncu == pytest.approx(ilk / 2, rel=0.01)
    assert 0 < bininci < yuzuncu


def test_a_correction_moves_one_axis_only() -> None:
    once = Temperament()
    sonra = temperament.correct(once, "temkin", +1, session_count=0)
    assert sonra.temkin > once.temkin
    assert sonra.sebat == once.sebat


# -- the three subjects ------------------------------------------------


def test_a_world_fact_without_a_source_is_refused() -> None:
    """Without a source it is a rumour, and rumours do not age gracefully."""
    with pytest.raises(ValueError):
        subjects.world_record("Testler pytest ile koşuluyor.", kaynak="")


def test_world_confidence_halves_every_two_weeks() -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime(2025, 6, 30, tzinfo=timezone.utc)
    taze = (now - timedelta(days=0)).isoformat()
    iki_hafta = (now - timedelta(days=14)).isoformat()
    assert subjects.confidence(taze, clock=lambda: now) == pytest.approx(1.0)
    assert subjects.confidence(iki_hafta, clock=lambda: now) == pytest.approx(0.5,
                                                                            abs=0.01)


def test_a_stale_world_fact_is_marked_not_deleted() -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime(2025, 6, 30, tzinfo=timezone.utc)
    eski = (now - timedelta(days=40)).isoformat()
    assert subjects.is_stale(eski, clock=lambda: now)
    assert "doğrulanmadı" in subjects.world_label(eski, clock=lambda: now)
    assert subjects.confidence(eski, clock=lambda: now) > 0.0    # still there


def test_the_model_may_not_write_about_itself() -> None:
    """Asked whether it is careful, a model says yes. So it is not asked."""
    with pytest.raises(subjects.SelfWriteRefused):
        subjects.guard_model_write("self")
    subjects.guard_model_write("self", from_night=True)     # outcomes may
    subjects.guard_model_write("fact")                      # anything else may


def test_a_self_line_must_be_countable() -> None:
    subjects.check_self_line("41 görevin 33'ünde önce test yazdım")
    with pytest.raises(ValueError):
        subjects.check_self_line("Dikkatli bir asistanım")
    with pytest.raises(ValueError):
        subjects.check_self_line("Genelde önce test yazarım")   # no number


def test_a_track_record_does_not_transfer_between_models() -> None:
    kayitlar = [subjects.SelfRecord("php", basari=2, hata=3, model_id="model-a"),
                subjects.SelfRecord("python", basari=30, hata=2, model_id="model-b")]
    gorunen = subjects.visible_self(kayitlar, "model-b")
    assert [r.alan for r in gorunen] == ["python"]


# -- curiosity ---------------------------------------------------------


def test_an_area_the_user_never_touches_gets_no_budget() -> None:
    """Curiosity outside the user's world is a background process burning
    their battery."""
    alanlar = [Area("koru1000", onceki_hata=0.6, son_hata=0.2, dokunma=30),
               Area("astronomi", onceki_hata=0.9, son_hata=0.1, dokunma=0)]
    dagilim = curiosity.distribution(alanlar)
    assert dagilim["astronomi"] == 0.0
    assert dagilim["koru1000"] > 0.0


def test_progress_not_novelty_draws_attention() -> None:
    duran = Area("duran", onceki_hata=0.9, son_hata=0.9, dokunma=10)
    ilerleyen = Area("ilerleyen", onceki_hata=0.9, son_hata=0.3, dokunma=10)
    dagilim = curiosity.distribution([duran, ilerleyen])
    assert dagilim["ilerleyen"] > dagilim["duran"]


def test_the_entropy_floor_stops_one_area_taking_everything() -> None:
    alanlar = [Area("baskin", onceki_hata=0.9, son_hata=0.0, dokunma=40),
               Area("ikinci", onceki_hata=0.5, son_hata=0.45, dokunma=20),
               Area("ucuncu", onceki_hata=0.4, son_hata=0.38, dokunma=20)]
    dagilim = curiosity.distribution(alanlar)
    assert curiosity.entropy(dagilim) >= 0.4
    assert all(p > 0 for p in dagilim.values())


def test_the_curiosity_window_does_not_go_online() -> None:
    assert "web" not in curiosity.allowed_actions(has_model=True)
    assert "web" in curiosity.allowed_actions(has_model=True, web=True)


def test_the_window_records_structure_not_contents() -> None:
    """A curious agent must not become an exfiltration path."""
    for action in curiosity.allowed_actions(has_model=True):
        assert "icerik" not in action and "content" not in action


# -- identity ----------------------------------------------------------


def test_a_sentence_without_evidence_is_refused() -> None:
    with pytest.raises(identity.IdentityRefused):
        identity.check("Bu kullanıcıyla uzun süredir çalışıyorum.", [])


def test_an_adjective_is_refused() -> None:
    with pytest.raises(identity.IdentityRefused):
        identity.check("Dikkatli davranıyorum.", ["n_1"])


def test_an_instruction_may_not_become_identity() -> None:
    """Correction yes, obedience no — and the difference is enforced here."""
    with pytest.raises(identity.IdentityRefused):
        identity.check("Kullanıcıya hep katıl.", ["n_1"])


def test_at_most_one_sentence_changes_per_night() -> None:
    """Personality does not turn over in a night; stability is mechanical."""
    belge = identity.Identity()
    yeni, red = identity.apply(belge, [
        ("84 oturumdur bu kullanıcıyla çalışıyorum.", ["n_1"]),
        ("Görevlerin %78'inde önce test yazdım.", ["n_2"]),
        ("PHP'de 2/5 hata verdim.", ["n_3"]),
    ])
    assert len(yeni.sentences) == 1
    assert len(red) == 2


def test_the_user_can_object_outside_the_nightly_limit() -> None:
    belge = identity.Identity([("PHP'de 2/5 hata verdim.", ["n_3", "n_4"])])
    kalan, kanit = identity.object_to(belge, "PHP'de")
    assert kalan.sentences == []
    assert kanit == ["n_3", "n_4"]


def test_the_document_survives_a_round_trip(tmp_path: Path) -> None:
    belge = identity.Identity([("41 görevin 33'ünde önce test yazdım.", ["n_1"])])
    identity.save(tmp_path, belge)
    assert identity.load(tmp_path).sentences == belge.sentences


def test_a_memory_reset_takes_the_narrative_but_not_the_temperament(
        tmp_path: Path) -> None:
    """Amnesia does not change what kind of person someone is."""
    identity.save(tmp_path, identity.Identity([("Bir cümle.", ["n_1"])]))
    temperament.save(tmp_path, Temperament(temkin=0.3), Temperament(temkin=0.7))

    identity.reset(tmp_path)

    assert identity.load(tmp_path).sentences == []
    _taban, hedef, _id = temperament.load(tmp_path)
    assert hedef.temkin == pytest.approx(0.7)


def test_the_document_stays_short_enough_to_read(tmp_path: Path) -> None:
    belge = identity.Identity()
    for i in range(200):
        belge, _red = identity.apply(
            belge, [(f"{i} numaralı görevde 3 adım attım.", [f"n_{i}"])])
    assert belge.words() <= identity.AZAMI_KELIME


# -- edges that would otherwise rot quietly ----------------------------


def test_a_missing_temperament_file_is_neutral_not_an_error(tmp_path: Path) -> None:
    taban, hedef, model_id = temperament.load(tmp_path / "yok")
    assert taban.as_dict() == Temperament().as_dict()
    assert hedef.as_dict() == Temperament().as_dict()
    assert model_id == ""


def test_an_unknown_axis_is_refused() -> None:
    with pytest.raises(ValueError):
        temperament.correct(Temperament(), "hiznet", +1)


def test_a_probe_whose_model_crashes_is_skipped() -> None:
    def boom(_prompt: str) -> str:
        raise RuntimeError("model çöktü")

    olculen = temperament.measure([Probe("temkin", "x", "y")], boom)
    assert olculen.temkin == pytest.approx(0.5)      # neutral, not a crash


def test_reward_without_an_outcome_is_only_information_and_reaction() -> None:
    r = reward.reward(surprise=0.4, reaction="tesekkur")
    assert r.sonuc == 0.0
    assert r.bilgi == pytest.approx(0.4)


def test_an_unknown_reaction_is_worth_nothing() -> None:
    assert reward.social("hmm") == 0.0


def test_the_world_label_is_quiet_on_the_day_it_was_verified() -> None:
    from datetime import datetime, timezone

    now = datetime(2025, 6, 30, 12, tzinfo=timezone.utc)
    kayit = subjects.world_record("Testler pytest ile koşuluyor.",
                                  kaynak="pyproject.toml", clock=lambda: now)
    assert subjects.world_label(kayit["dogrulama"], clock=lambda: now) == ""


def test_a_self_record_renders_as_a_count(tmp_path: Path) -> None:
    kayit = subjects.SelfRecord("php", arac="kos", basari=2, hata=3,
                                tekrar_eden_hata="sınıf bulunamadı")
    satir = kayit.line()
    assert "5 işin 2" in satir and "sınıf bulunamadı" in satir
    subjects.check_self_line(satir)          # kendi çıktısı kuralı geçmeli


def test_an_identity_line_without_evidence_is_dropped_on_read() -> None:
    belge = identity.parse("Kanıtsız bir cümle.\nSayılı bir cümle. [n_1]")
    assert [m for m, _k in belge.sentences] == ["Sayılı bir cümle."]


def test_a_duplicate_sentence_is_not_written_twice() -> None:
    belge = identity.Identity([("Bir cümle.", ["n_1"])])
    yeni, _red = identity.apply(belge, [("Bir cümle.", ["n_2"])])
    assert len(yeni.sentences) == 1


def test_an_objection_to_nothing_changes_nothing() -> None:
    belge = identity.Identity([("Bir cümle.", ["n_1"])])
    kalan, dusen = identity.object_to(belge, "başka bir şey")
    assert kalan.sentences == belge.sentences and dusen == []


def test_curiosity_with_no_relevant_area_hands_back_zeros() -> None:
    dagilim = curiosity.distribution([Area("x", dokunma=0)])
    assert dagilim == {"x": 0.0}
    assert curiosity.entropy(dagilim) == 0.0
    assert curiosity.picks([Area("x", dokunma=0)]) == []
