#!/usr/bin/env python3
"""Calculate cloud costs for AWS, GCP, and Azure."""
import json
import argparse
import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any
from abc import ABC, abstractmethod

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class ResourceMetrics:
    total_wall_clock_s: float
    peak_memory_mb: float
    storage_total_gb: float
    storage_findata_gb: float
    network_ingress_mb: float
    network_egress_mb: float
    io_read_operations: int
    io_write_operations: int

    @classmethod
    def load(cls, path: Path):
        with open(path) as f:
            d = json.load(f)
        return cls(
            d.get("total_wall_clock_s", 600),
            d.get("peak_memory_mb", 512),
            d.get("storage_total_gb", 2.5),
            d.get("storage_findata_gb", 2.0),
            d.get("network_ingress_mb", 9),
            d.get("network_egress_mb", 0.1),
            d.get("io_read_operations", 2000),
            d.get("io_write_operations", 200),
        )


class CloudPricing(ABC):
    def __init__(self, config: Dict, metrics: ResourceMetrics):
        self.config = config
        self.metrics = metrics

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def region(self) -> str:
        pass

    @abstractmethod
    def calc_compute(self, n: int) -> Dict:
        pass

    @abstractmethod
    def calc_storage(self) -> Dict:
        pass

    @abstractmethod
    def calc_network(self, pv: int) -> Dict:
        pass

    @abstractmethod
    def calc_scheduling(self, n: int) -> float:
        pass

    def calculate_all(self, executions: int, page_views: int) -> Dict:
        compute = self.calc_compute(executions)
        storage = self.calc_storage()
        network = self.calc_network(page_views)
        sched = self.calc_scheduling(executions)

        min_cost, best = float("inf"), ""
        for inst, models in compute.items():
            for model, cost in models.items():
                if cost < min_cost:
                    min_cost, best = cost, f"{inst} ({model})"

        st, nt = sum(storage.values()), sum(network.values())
        return {
            "provider": self.name,
            "region": self.region,
            "compute": compute,
            "storage": storage,
            "network": network,
            "scheduling": sched,
            "totals": {
                "storage": round(st, 4),
                "network": round(nt, 4),
                "scheduling": round(sched, 4),
            },
            "recommended": {
                "config": best,
                "compute_monthly": round(min_cost, 4),
                "total_monthly": round(min_cost + st + nt + sched, 4),
            },
        }


class AWSPricing(CloudPricing):
    @property
    def name(self):
        return "AWS"

    @property
    def region(self):
        return self.config["pricing"]["aws"]["region"]

    def calc_compute(self, n):
        p = self.config["pricing"]["aws"]["compute"]
        h = (self.metrics.total_wall_clock_s / 3600) * n
        return {
            i: {
                "spot": round(r["spot_hourly"] * h, 4),
                "on_demand": round(r["on_demand_hourly"] * h, 4),
                "reserved": round(r["reserved_1yr_hourly"] * h, 4),
            }
            for i, r in p.items()
        }

    def calc_storage(self):
        p = self.config["pricing"]["aws"]["storage"]
        return {
            "object_storage": round(
                self.metrics.storage_total_gb * p["s3_standard_gb_month"], 4
            ),
            "api_operations": round(
                (self.metrics.io_write_operations / 1000) * p["s3_put_per_1000"]
                + (self.metrics.io_read_operations / 1000) * p["s3_get_per_1000"],
                4,
            ),
        }

    def calc_network(self, pv):
        p = self.config["pricing"]["aws"]["network"]
        gb = (pv * self.config["default_parameters"].get("avg_page_size_mb", 0.5)) / 1024
        return {
            "cdn_egress": round(gb * p["cloudfront_gb_first_10tb"], 4),
            "data_transfer": 0.0,
        }

    def calc_scheduling(self, n):
        return 0.0


class GCPPricing(CloudPricing):
    @property
    def name(self):
        return "GCP"

    @property
    def region(self):
        return self.config["pricing"]["gcp"]["region"]

    def calc_compute(self, n):
        p = self.config["pricing"]["gcp"]["compute"]
        h = (self.metrics.total_wall_clock_s / 3600) * n
        return {
            i: {
                "preemptible": round(r["preemptible_hourly"] * h, 4),
                "on_demand": round(r["on_demand_hourly"] * h, 4),
                "committed": round(r["committed_1yr_hourly"] * h, 4),
            }
            for i, r in p.items()
        }

    def calc_storage(self):
        p = self.config["pricing"]["gcp"]["storage"]
        return {
            "object_storage": round(
                self.metrics.storage_total_gb * p["gcs_standard_gb_month"], 4
            ),
            "api_operations": round(
                (self.metrics.io_write_operations / 10000) * p["gcs_class_a_per_10000"]
                + (self.metrics.io_read_operations / 10000) * p["gcs_class_b_per_10000"],
                4,
            ),
        }

    def calc_network(self, pv):
        p = self.config["pricing"]["gcp"]["network"]
        gb = (pv * self.config["default_parameters"].get("avg_page_size_mb", 0.5)) / 1024
        return {
            "cdn_egress": round(gb * p["cloud_cdn_gb_first_10tb"], 4),
            "data_transfer": 0.0,
        }

    def calc_scheduling(self, n):
        return 0.0


class AzurePricing(CloudPricing):
    @property
    def name(self):
        return "Azure"

    @property
    def region(self):
        return self.config["pricing"]["azure"]["region"]

    def calc_compute(self, n):
        p = self.config["pricing"]["azure"]["compute"]
        h = (self.metrics.total_wall_clock_s / 3600) * n
        return {
            i: {
                "spot": round(r["spot_hourly"] * h, 4),
                "on_demand": round(r["on_demand_hourly"] * h, 4),
                "reserved": round(r["reserved_1yr_hourly"] * h, 4),
            }
            for i, r in p.items()
        }

    def calc_storage(self):
        p = self.config["pricing"]["azure"]["storage"]
        return {
            "object_storage": round(
                self.metrics.storage_total_gb * p["blob_hot_gb_month"], 4
            ),
            "api_operations": round(
                (self.metrics.io_write_operations / 10000) * p["blob_write_per_10000"]
                + (self.metrics.io_read_operations / 10000) * p["blob_read_per_10000"],
                4,
            ),
        }

    def calc_network(self, pv):
        p = self.config["pricing"]["azure"]["network"]
        gb = (pv * self.config["default_parameters"].get("avg_page_size_mb", 0.5)) / 1024
        return {
            "cdn_egress": round(gb * p["cdn_gb_first_10tb"], 4),
            "data_transfer": 0.0,
        }

    def calc_scheduling(self, n):
        return round(
            n * self.config["pricing"]["azure"]["scheduling"]["logic_apps_per_execution"],
            4,
        )


def print_table(results, metrics, executions, page_views):
    print()
    print("=" * 78)
    print(
        f"  CLOUD COST COMPARISON - {executions} runs/month, {page_views} page views - Brazil Region"
    )
    print("=" * 78)
    print(
        f"  Measured: {metrics.peak_memory_mb:.0f} MB memory | "
        f"{metrics.total_wall_clock_s/60:.1f} min runtime | "
        f"{metrics.storage_total_gb:.2f} GB storage"
    )

    print("\n  MONTHLY COMPUTE")
    print("  " + "-" * 74)
    print(
        f"  {'Provider':<8} | {'Instance':<10} | {'Spot/Preempt':>12} | {'On-Demand':>11} | {'Reserved':>10}"
    )
    print("  " + "-" * 74)
    for prov, data in results.items():
        for inst, costs in data["compute"].items():
            sk = "spot" if "spot" in costs else "preemptible"
            rk = "reserved" if "reserved" in costs else "committed"
            print(
                f"  {prov:<8} | {inst:<10} | ${costs[sk]:>10.4f} | "
                f"${costs['on_demand']:>9.4f} | ${costs[rk]:>8.4f}"
            )

    print("\n  MONTHLY STORAGE + NETWORK")
    print("  " + "-" * 74)
    print(
        f"  {'Provider':<8} | {'Object Storage':>15} | {'API Ops':>10} | {'CDN/Egress':>12} | {'Total':>10}"
    )
    print("  " + "-" * 74)
    for prov, data in results.items():
        s, n = data["storage"], data["network"]
        t = data["totals"]["storage"] + data["totals"]["network"]
        print(
            f"  {prov:<8} | ${s['object_storage']:>13.4f} | "
            f"${s['api_operations']:>8.4f} | ${n['cdn_egress']:>10.4f} | ${t:>8.4f}"
        )

    print("\n" + "=" * 78)
    print("  RECOMMENDATION (Cheapest: Small Instance + Spot/Preemptible)")
    print("  " + "-" * 74)
    recs = sorted(
        [
            (p, d["recommended"]["total_monthly"], d["recommended"]["config"])
            for p, d in results.items()
        ],
        key=lambda x: x[1],
    )
    for i, (p, c, cfg) in enumerate(recs):
        marker = "->" if i == 0 else "  "
        print(f"  {marker} {p:<6}: ${c:.4f}/month ({cfg})")
    print("=" * 78)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executions", type=int, default=22)
    parser.add_argument("--page-views", type=int, default=100)
    parser.add_argument(
        "--provider", default="all", choices=["aws", "gcp", "azure", "all"]
    )
    parser.add_argument("--metrics", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    cfg_path = (
        Path(args.config)
        if args.config
        else PROJECT_ROOT / "parameters" / "cloud_pricing_config.json"
    )
    with open(cfg_path) as f:
        config = json.load(f)

    met_path = (
        Path(args.metrics)
        if args.metrics
        else PROJECT_ROOT / "data" / "results" / "resource_metrics.json"
    )
    if met_path.exists():
        metrics = ResourceMetrics.load(met_path)
    else:
        print("Warning: Metrics not found, using defaults")
        metrics = ResourceMetrics(600, 512, 2.5, 2.0, 9, 0.1, 2000, 200)

    providers = {"aws": AWSPricing, "gcp": GCPPricing, "azure": AzurePricing}
    selected = [args.provider] if args.provider != "all" else ["aws", "gcp", "azure"]
    results = {
        n.upper(): providers[n](config, metrics).calculate_all(
            args.executions, args.page_views
        )
        for n in selected
    }

    print_table(results, metrics, args.executions, args.page_views)

    out_path = (
        Path(args.output)
        if args.output
        else PROJECT_ROOT / "data" / "results" / "cloud_cost_comparison.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "generated_at": datetime.datetime.now().isoformat(),
        "parameters": {
            "executions_month": args.executions,
            "page_views_month": args.page_views,
        },
        "measured_resources": {
            "peak_memory_mb": metrics.peak_memory_mb,
            "runtime_minutes": round(metrics.total_wall_clock_s / 60, 2),
            "storage_gb": metrics.storage_total_gb,
        },
        "providers": results,
    }
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
