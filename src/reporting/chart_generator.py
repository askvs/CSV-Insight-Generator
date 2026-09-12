# Fallback chart generator for reports
import io
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


# Create a summary bar chart when no code chart was created by the agent
def generate_fallback_chart(df: pd.DataFrame | None = None) -> bytes | None:
    if df is None or len(df) == 0:
        return None
    try:
        fig, ax = plt.subplots(figsize=(9, 4.2), dpi=120)
        plt.style.use(
            "seaborn-v0_8-whitegrid"
            if "seaborn-v0_8-whitegrid" in plt.style.available
            else "default"
        )

        num_cols = df.select_dtypes(include=["number"]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        if cat_cols and num_cols:
            cat = cat_cols[0]
            num = num_cols[0]
            top_cats = df[cat].value_counts().head(8).index
            sub_df = df[df[cat].isin(top_cats)]
            avg_vals = sub_df.groupby(cat)[num].mean().sort_values(ascending=False)

            colors_list = [
                "#1D4ED8",
                "#2563EB",
                "#3B82F6",
                "#60A5FA",
                "#93C5FD",
                "#BFDBFE",
                "#DBEAFE",
                "#EFF6FF",
            ]
            avg_vals.plot(
                kind="bar",
                ax=ax,
                color=colors_list[: len(avg_vals)],
                edgecolor="#0F2942",
                linewidth=0.8,
            )
            ax.set_title(
                f"Empirical Average {num} by {cat}",
                fontsize=12,
                fontweight="bold",
                pad=12,
                color="#0F2942",
            )
            ax.set_ylabel(f"Average {num}", fontsize=10, color="#1E293B")
            ax.set_xlabel(cat, fontsize=10, color="#1E293B")
            ax.tick_params(axis="x", rotation=25)
        elif len(num_cols) >= 2:
            df[num_cols[:5]].mean().plot(
                kind="bar", ax=ax, color="#1D4ED8", edgecolor="#0F2942"
            )
            ax.set_title(
                "Dataset Numeric Baseline Averages",
                fontsize=12,
                fontweight="bold",
                pad=12,
                color="#0F2942",
            )
            ax.set_ylabel("Metric Mean", fontsize=10)
            ax.tick_params(axis="x", rotation=20)
        else:
            return None

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=120)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        plt.close("all")
        return None
