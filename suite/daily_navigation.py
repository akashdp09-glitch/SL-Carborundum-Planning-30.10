"""Stable Daily Plan shortcuts: never rely on positions in a mutable list."""
def focus_labels(options):
    prefixes={'wip':'🏭 WIP','closed':'📊 Daily Open','status':'📡 Daily Status','kpi':'🎯 Monthly','planning_kpi':'🎯 Monthly','download':'⬇️ Download','capacity':'🏭 All-section','capacity_actual':'⚖️ Capacity','mixing':'⚙️ Mixing','daily':'📅 Daily plan','section':'📅 Daily plan'}
    return {key:next((label for label in options if label.startswith(prefix)),options[0] if options else '') for key,prefix in prefixes.items()}
