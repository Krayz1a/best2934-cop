"""Rendering only local truth (book rules 8, 9)."""

from __future__ import annotations

from p2pchase.ui.board_render import (
    GLYPH_BARRIER,
    GLYPH_ME,
    SHADES,
    belief_grid,
    render_board,
    render_frame,
    render_legend,
    render_status,
    shade_for,
)

VIEW = {
    "role": "police",
    "step": 4,
    "my_position": [1, 1],
    "barriers": [[0, 0], [6, 6]],
    "barriers_left": 12,
    "belief": {"3,3": 0.5, "3,4": 0.25, "0,6": 0.01},
    "belief_top": [[[3, 3], 0.5]],
    "belief_entropy": 1.5,
    "hint_trust": 0.62,
    "tokens_used": 0,
}


def test_shading_is_scaled_against_the_current_peak():
    """A diffuse posterior never exceeds a few percent; an absolute scale is blank."""
    assert shade_for(0.05, 0.05) == SHADES[-1]
    assert shade_for(0.0, 0.05) == SHADES[0]
    assert shade_for(0.025, 0.05) == SHADES[len(SHADES) // 2]


def test_shading_copes_with_a_silent_board():
    assert shade_for(0.0, 0.0) == SHADES[0]
    assert shade_for(0.5, 0.0) == SHADES[0]


def test_the_grid_places_the_agent_and_its_walls():
    grid = belief_grid(VIEW)
    assert grid[1][1] == GLYPH_ME
    assert grid[0][0] == GLYPH_BARRIER
    assert grid[6][6] == GLYPH_BARRIER


def test_the_hottest_belief_cell_is_the_darkest_shade():
    grid = belief_grid(VIEW)
    assert grid[3][3] == SHADES[-1]
    assert grid[3][4] != SHADES[-1]


def test_the_rendered_board_has_one_row_per_grid_row():
    lines = render_board(VIEW).splitlines()
    assert len(lines) == 2 + 7 + 1  # header, top rule, seven rows, bottom rule
    assert lines[0].split() == [str(n) for n in range(7)]


def test_the_status_panel_reports_the_numbers_a_player_needs():
    text = render_status(VIEW)
    assert "police" in text
    assert "(3, 3)" in text
    assert "1.500 bits" in text
    assert "0.620" in text


def test_the_status_panel_copes_with_no_belief_yet():
    assert "unknown" in render_status({**VIEW, "belief_top": []})


def test_the_legend_states_what_is_deliberately_absent():
    """The absence is the design, so the picture says so out loud."""
    legend = render_legend()
    assert "opponent's true position is NOT shown" in legend
    assert "rules 8, 9" in legend


def test_a_frame_composes_banner_board_status_and_legend():
    frame = render_frame(VIEW, banner="live view")
    assert frame.startswith("live view")
    assert GLYPH_ME in frame
    assert "belief entropy" in frame
    assert "rules 8, 9" in frame


def test_a_renderer_cannot_be_handed_the_objective_board():
    """There is no parameter through which the truth could arrive."""
    import inspect

    for function in (belief_grid, render_board, render_status, render_frame):
        names = set(inspect.signature(function).parameters)
        assert not {"opponent", "opponent_position", "true_state", "world"} & names
