#!/usr/bin/env python3
"""Profile resource usage for cloud cost estimation."""
import os, sys, json, time, argparse, subprocess, threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass, field, asdict
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
try:
    import psutil
except ImportError:
    print("ERROR: pip install psutil>=5.9")
    sys.exit(1)
@dataclass  
class ResourceMetrics:
    generated_at: str = ""
    profiler_version: str = "1.1.0"
    pipelines_profiled: str = "A_Portfolio.sh, B_Ledger.sh"
    total_wall_clock_s: float = 0.0
    total_cpu_seconds: float = 0.0
    peak_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    # A_Portfolio pipeline metrics
    a_pipeline_wall_clock_s: float = 0.0
    a_pipeline_peak_memory_mb: float = 0.0
    # B_Ledger pipeline metrics
    b_pipeline_wall_clock_s: float = 0.0
    b_pipeline_peak_memory_mb: float = 0.0
    stages: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    storage_findata_gb: float = 0.0
    storage_html_gb: float = 0.0
    storage_results_gb: float = 0.0
    storage_parameters_gb: float = 0.0
    storage_engines_gb: float = 0.0
    storage_total_gb: float = 0.0
    file_count_findata: int = 0
    file_count_total: int = 0
    network_ingress_mb: float = 0.0
    network_egress_mb: float = 0.0
    io_read_operations: int = 0
    io_write_operations: int = 0
class ResourceProfiler:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.metrics = ResourceMetrics()
        self.monitoring = False
        self.memory_samples: List[float] = []
        self.cpu_samples: List[float] = []
    def calculate_storage(self) -> None:
        print("\n📁 Calculating storage usage...")
        directories = {
            'findata': self.project_root / 'data' / 'findata',
            'html': self.project_root / 'html',
            'results': self.project_root / 'data' / 'results',
            'parameters': self.project_root / 'parameters',
            'engines': self.project_root / 'engines',
        }
        total_size, total_files = 0, 0
        for name, path in directories.items():
            if not path.exists():
                continue
            size_bytes, file_count = 0, 0
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d != '__pycache__']
                for f in files:
                    if not f.startswith('.'):
                        try:
                            size_bytes += os.path.getsize(os.path.join(root, f))
                            file_count += 1
                        except: pass
            size_gb = size_bytes / (1024 ** 3)
            total_size += size_bytes
            total_files += file_count
            if hasattr(self.metrics, f'storage_{name}_gb'):
                setattr(self.metrics, f'storage_{name}_gb', round(size_gb, 4))
            if name == 'findata':
                self.metrics.file_count_findata = file_count
            print(f"  ✓ {name}: {size_gb:.3f} GB ({file_count:,} files)")
        self.metrics.storage_total_gb = round(total_size / (1024 ** 3), 4)
        self.metrics.file_count_total = total_files
    def estimate_network(self) -> None:
        tickers_file = self.project_root / 'parameters' / 'tickers.txt'
        ticker_count = 0
        if tickers_file.exists():
            with open(tickers_file) as f:
                ticker_count = sum(1 for l in f if l.strip() and not l.startswith('#') and not l.startswith('Ticker'))
        self.metrics.network_ingress_mb = round((ticker_count * 50) / 1024, 2)
        self.metrics.network_egress_mb = 0.1
        print(f"🌐 Network: {ticker_count} tickers, {self.metrics.network_ingress_mb:.2f} MB ingress")
    def estimate_io_operations(self) -> None:
        ticker_count = self.metrics.file_count_findata // 2500 if self.metrics.file_count_findata > 0 else 180
        self.metrics.io_read_operations = ticker_count * 10 + 500
        self.metrics.io_write_operations = 50 + ticker_count
        print(f"💾 I/O: ~{self.metrics.io_read_operations:,} reads, ~{self.metrics.io_write_operations:,} writes")
    def _monitor_resources(self, pid: int) -> None:
        try:
            proc = psutil.Process(pid)
        except: return
        while self.monitoring:
            try:
                mem = proc.memory_info().rss / (1024**2)
                for c in proc.children(recursive=True):
                    try: mem += c.memory_info().rss / (1024**2)
                    except: pass
                self.memory_samples.append(mem)
                self.cpu_samples.append(proc.cpu_percent())
            except: break
            time.sleep(0.5)
    def run_pipeline_with_profiling(self, script_name: str, stage_prefix: str) -> tuple:
        """Run a pipeline script and profile it. Returns (success, wall_clock_s, peak_memory_mb)"""
        script = self.project_root / 'engines' / script_name
        if not script.exists():
            print(f"❌ Not found: {script}")
            return False, 0.0, 0.0
        print(f"\n🚀 Running {script_name}...\n" + "="*70)
        start = time.time()
        proc = subprocess.Popen(['bash', str(script)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                cwd=str(self.project_root), text=True, bufsize=1)
        self.monitoring, self.memory_samples, self.cpu_samples = True, [], []
        t = threading.Thread(target=self._monitor_resources, args=(proc.pid,), daemon=True)
        t.start()
        stage, stage_start, stages = None, start, {}
        for line in proc.stdout:
            print(line.rstrip())
            if 'Starting' in line and 'stage' in line:
                if stage: stages[stage] = time.time() - stage_start
                # Detect A_Portfolio stages
                if 'Download' in line:
                    stage = f'{stage_prefix}_Download'
                elif 'Scoring' in line:
                    stage = f'{stage_prefix}_Scoring'
                elif 'Portfolio' in line:
                    stage = f'{stage_prefix}_Portfolio'
                elif 'Analysis' in line:
                    stage = f'{stage_prefix}_Analysis'
                else:
                    stage = f'{stage_prefix}_Other'
                stage_start = time.time()
            # Detect B_Ledger stages
            elif 'ProcessNotes' in line or 'Process_Notes' in line:
                if stage: stages[stage] = time.time() - stage_start
                stage = f'{stage_prefix}_ProcessNotes'
                stage_start = time.time()
            elif 'Consolidate' in line:
                if stage: stages[stage] = time.time() - stage_start
                stage = f'{stage_prefix}_Consolidate'
                stage_start = time.time()
            elif 'Generate' in line and 'assets' in line.lower():
                if stage: stages[stage] = time.time() - stage_start
                stage = f'{stage_prefix}_GenerateAssets'
                stage_start = time.time()
            elif 'portfolio history' in line.lower():
                if stage: stages[stage] = time.time() - stage_start
                stage = f'{stage_prefix}_PortfolioHistory'
                stage_start = time.time()
        proc.wait()
        self.monitoring = False
        t.join(timeout=2)
        if stage: stages[stage] = time.time() - stage_start
        print("="*70)
        wall_clock = round(time.time() - start, 2)
        peak_mem = round(max(self.memory_samples), 2) if self.memory_samples else 0.0
        for s, d in stages.items():
            self.metrics.stages[s] = {'wall_clock_s': round(d,2), 'status': 'completed'}
        print(f"\n{'✅' if proc.returncode==0 else '❌'} {script_name}: {wall_clock:.1f}s, {peak_mem:.1f}MB")
        return proc.returncode == 0, wall_clock, peak_mem
    def load_from_logs(self) -> bool:
        print("\n📊 Loading from logs...")
        try:
            import pandas as pd
            total_a = 0
            for name, fn in [('A_Download','download_performance.csv'),('A_Scoring','scoring_performance.csv'),
                             ('A_Portfolio','portfolio_performance.csv')]:
                p = self.project_root/'data'/'results'/fn
                if p.exists():
                    df = pd.read_csv(p)
                    if not df.empty:
                        avg = df['overall_script_duration_s'].tail(10).mean()
                        self.metrics.stages[name] = {'wall_clock_s': round(avg,2), 'status': 'from_logs'}
                        total_a += avg
                        print(f"  ✓ {name}: {avg:.1f}s")

            # Estimate B_Ledger (typically runs in <30 seconds)
            b_ledger_estimate = 30.0  # Conservative estimate
            self.metrics.stages['B_ProcessNotes'] = {'wall_clock_s': 10.0, 'status': 'estimated'}
            self.metrics.stages['B_Consolidate'] = {'wall_clock_s': 5.0, 'status': 'estimated'}
            self.metrics.stages['B_GenerateAssets'] = {'wall_clock_s': 5.0, 'status': 'estimated'}
            self.metrics.stages['B_PortfolioHistory'] = {'wall_clock_s': 10.0, 'status': 'estimated'}
            print(f"  ✓ B_Ledger (estimated): {b_ledger_estimate:.1f}s")

            if total_a > 0:
                self.metrics.a_pipeline_wall_clock_s = round(total_a, 2)
                self.metrics.b_pipeline_wall_clock_s = b_ledger_estimate
                self.metrics.total_wall_clock_s = round(total_a + b_ledger_estimate, 2)
                self.metrics.peak_memory_mb = 512
                self.metrics.a_pipeline_peak_memory_mb = 512
                self.metrics.b_pipeline_peak_memory_mb = 256
                return True
        except Exception as e: print(f"  ⚠️ {e}")
        return False
    def generate_metrics(self, full_run: bool = True):
        self.metrics.generated_at = datetime.now().isoformat()
        self.calculate_storage()
        self.estimate_network()
        self.estimate_io_operations()
        if full_run:
            # Run A_Portfolio.sh
            print("\n" + "="*70)
            print("  PROFILING PIPELINE 1/2: A_Portfolio.sh (stock analysis)")
            print("="*70)
            success_a, time_a, mem_a = self.run_pipeline_with_profiling('A_Portfolio.sh', 'A')
            self.metrics.a_pipeline_wall_clock_s = time_a
            self.metrics.a_pipeline_peak_memory_mb = mem_a

            # Run B_Ledger.sh
            print("\n" + "="*70)
            print("  PROFILING PIPELINE 2/2: B_Ledger.sh (transaction processing)")
            print("="*70)
            success_b, time_b, mem_b = self.run_pipeline_with_profiling('B_Ledger.sh', 'B')
            self.metrics.b_pipeline_wall_clock_s = time_b
            self.metrics.b_pipeline_peak_memory_mb = mem_b

            # Aggregate totals
            self.metrics.total_wall_clock_s = time_a + time_b
            self.metrics.peak_memory_mb = max(mem_a, mem_b)

            if not success_a and not success_b:
                self.load_from_logs()
        else:
            self.load_from_logs()
        return self.metrics
    def save_metrics(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f: json.dump(asdict(self.metrics), f, indent=2)
        print(f"\n💾 Saved: {path}")
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-run', action='store_true')
    parser.add_argument('--output', type=str, default=None)
    args = parser.parse_args()
    out = Path(args.output) if args.output else PROJECT_ROOT/'data'/'results'/'resource_metrics.json'
    print("="*70 + "\n  RESOURCE PROFILER\n" + "="*70)
    p = ResourceProfiler(PROJECT_ROOT)
    p.generate_metrics(full_run=not args.no_run)
    p.save_metrics(out)
    print("\n✅ Done! Run 'python scripts/cloud_pricing.py' next")
if __name__ == '__main__': main()
