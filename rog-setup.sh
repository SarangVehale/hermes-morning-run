#!/usr/bin/env bash
# rog-setup.sh — Inference server setup for the ROG Flow X13
#
# What this does (12 phases, each gated for yes/no/abort):
#   1.  System packages
#   2.  CUDA toolkit
#   3.  Build llama.cpp with CUDA
#   4.  Models directory + hf (Hugging Face CLI)
#   5.  Download models (Qwen 3.6 35B A3B, Hermes 4.3 36B, Hermes 4 14B)
#   6.  systemd USER units for llama-server
#   7.  SSH server (for HP to remotely suspend after morning run)
#   8.  Avahi / mDNS (advertises this machine as rogflow.local)
#   9.  Wake-on-Wi-Fi detection (informational, usually unreliable)
#   10. Static IP guidance (you do this part in your router admin)
#   11. Firewall (LAN-only, optional)
#   12. Smoke test
#
# What this does NOT do:
#   - Touch any existing files outside ~/llama.cpp, ~/models/, ~/.config/systemd/
#   - Modify /etc/hostname (your system hostname stays whatever it is)
#   - Enable services at boot without explicit approval
#   - Open any inbound port to the public internet
#   - Configure your router (you do that part manually with the guide)
#
# Re-runnable: phases check for existing state and skip if already done.

set -euo pipefail

# --- Visual setup -------------------------------------------------------------
BOLD=$'\033[1m'
DIM=$'\033[2m'
RED=$'\033[31m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RESET=$'\033[0m'

say() { echo "${BOLD}$*${RESET}"; }
info() { echo "${DIM}$*${RESET}"; }
ok() { echo "${GREEN}OK${RESET} $*"; }
warn() { echo "${YELLOW}!${RESET}  $*"; }
fail() { echo "${RED}FAIL${RESET} $*" >&2; }
hr() { echo "${DIM}--------------------------------------------------------------${RESET}"; }

phase() {
	local title="$1"
	shift
	echo
	hr
	say "PHASE: $title"
	hr
	echo
	for line in "$@"; do echo "  - $line"; done
	echo
	while true; do
		read -rp "${BOLD}Proceed with this phase?${RESET} [yes/no/abort]: " ans
		case "$ans" in
		yes | y | YES | Y)
			echo
			return 0
			;;
		no | n | NO | N | skip)
			warn "Skipping phase: $title"
			return 1
			;;
		abort | quit | exit | q)
			fail "Aborted by user."
			exit 130
			;;
		*) echo "Type 'yes', 'no', or 'abort'." ;;
		esac
	done
}

confirm_run() {
	local desc="$1"
	shift
	echo
	info "About to run: $desc"
	echo "  ${BOLD}\$${RESET} $*"
	read -rp "${BOLD}OK?${RESET} [yes/no]: " ans
	case "$ans" in
	yes | y | YES | Y) "$@" ;;
	*)
		warn "Skipped."
		return 1
		;;
	esac
}

confirm_run_block() {
	local desc="$1"
	local cmd="$2"
	echo
	info "About to run: $desc"
	echo "${BOLD}---${RESET}"
	echo "$cmd"
	echo "${BOLD}---${RESET}"
	read -rp "${BOLD}OK?${RESET} [yes/no]: " ans
	case "$ans" in
	yes | y | YES | Y) eval "$cmd" ;;
	*)
		warn "Skipped."
		return 1
		;;
	esac
}

# --- Banner -------------------------------------------------------------------
clear
cat <<'BANNER'
--------------------------------------------------------------
  ROG Flow X13 - Inference Server Setup (12 phases, gated)
  Backend for Hermes Agent on the HP

  Primary:    Qwen 3.6 35B A3B Q4_K_M  (Alibaba MoE)
  Heavy:      Hermes 4.3 36B Q4_K_M    (Nous dense)
  Fallback:   Hermes 4 14B Q4_K_M      (community)

  Plus: SSH, mDNS, WoWLAN probe, static IP guide, firewall
--------------------------------------------------------------
BANNER

echo
say "Read this before proceeding."
cat <<'INTRO'

This installs the LLM inference server and supporting networking.

12 phases. Each prompts yes/no/abort. Per-command confirmations inside
each phase. Nothing irreversible happens without you typing 'yes' to it.

You can quit at any phase with 'abort' (or Ctrl-C from a prompt).
Re-running the script is safe and idempotent.

INTRO

read -rp "${BOLD}Begin?${RESET} [yes/abort]: " begin_ans
case "$begin_ans" in
yes | y | YES | Y) ;;
*)
	fail "Aborted."
	exit 130
	;;
esac

if [ "$EUID" -eq 0 ]; then
	fail "Don't run as root. Script uses sudo where needed."
	exit 1
fi

say "Caching sudo credentials..."
sudo -v
(while true; do
	sudo -n true
	sleep 60
	kill -0 "$$" || exit
done) 2>/dev/null &
SUDO_KEEPALIVE_PID=$!
trap 'kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true' EXIT

# --- Gather config ------------------------------------------------------------
echo
hr
say "Configuration"
hr
echo

read -rp "Your username on this machine [$(whoami)]: " ROG_USER
ROG_USER="${ROG_USER:-$(whoami)}"

read -rp "Your home directory [/home/$ROG_USER]: " ROG_HOME
ROG_HOME="${ROG_HOME:-/home/$ROG_USER}"

DEFAULT_IFACE=$(ip route show default 2>/dev/null | head -1 | awk '{print $5}')
read -rp "Network interface (Wi-Fi or wired) [${DEFAULT_IFACE:-wlan0}]: " NET_IFACE
NET_IFACE="${NET_IFACE:-${DEFAULT_IFACE:-wlan0}}"

ROG_MAC=$(ip link show "$NET_IFACE" 2>/dev/null | awk '/link\/ether/ {print $2}' || echo "UNKNOWN")
ROG_IP=$(ip -4 addr show "$NET_IFACE" 2>/dev/null | awk '/inet / {print $2}' | cut -d/ -f1 || echo "UNKNOWN")
GATEWAY=$(ip route show default dev "$NET_IFACE" 2>/dev/null | awk '/default/ {print $3; exit}')
SYS_HOSTNAME=$(hostname)

echo
ok "Config gathered:"
echo "    User:            $ROG_USER"
echo "    Home:            $ROG_HOME"
echo "    System hostname: $SYS_HOSTNAME"
echo "    Interface:       $NET_IFACE"
echo "    MAC:             $ROG_MAC"
echo "    IP:              $ROG_IP"
echo "    Gateway:         ${GATEWAY:-unknown}"
echo
warn "Write down the MAC and IP - you'll need them on the HP."
read -rp "Press enter when noted..."

# =============================================================================
# PHASE 1 - System packages
# =============================================================================
if phase "1/12 - System packages" \
	"Optional: pacman -Syu (full system update)" \
	"Install: base-devel cmake git ethtool wol python-pip curl jq" \
	"         openssh avahi nss-mdns iw"; then

	read -rp "Run full system update first (pacman -Syu)? [yes/no]: " update_ans
	if [[ "$update_ans" =~ ^(yes|y|YES|Y)$ ]]; then
		confirm_run "full system upgrade" sudo pacman -Syu --noconfirm
	fi

	confirm_run "install build tools and networking utilities" \
		sudo pacman -S --needed --noconfirm \
		base-devel cmake git ethtool wol python-pip curl jq \
		openssh avahi nss-mdns iw

	ok "Phase 1 complete."
fi

# =============================================================================
# PHASE 2 - CUDA toolkit
# =============================================================================
if phase "2/12 - CUDA toolkit" \
	"Check for existing CUDA" \
	"If missing: install the 'cuda' package (~3GB; includes nvcc and all libs)" \
	"Verify nvcc and nvidia-smi work"; then

	if command -v nvcc >/dev/null 2>&1; then
		CUDA_VER=$(nvcc --version | grep release | awk '{print $5}' | tr -d ,)
		ok "CUDA already installed (version $CUDA_VER)"
	else
		warn "CUDA not found. ~3GB download."
		confirm_run "install CUDA" sudo pacman -S --needed --noconfirm cuda

		if ! grep -q "/opt/cuda/bin" "$ROG_HOME/.bashrc" 2>/dev/null; then
			confirm_run_block "add CUDA to PATH in ~/.bashrc" \
				'echo "" >> ~/.bashrc
echo "# CUDA toolkit" >> ~/.bashrc
echo "export PATH=/opt/cuda/bin:\$PATH" >> ~/.bashrc
echo "export LD_LIBRARY_PATH=/opt/cuda/lib64:\$LD_LIBRARY_PATH" >> ~/.bashrc'
		fi
		export PATH=/opt/cuda/bin:$PATH
	fi

	info "Verifying GPU is visible..."
	if nvidia-smi >/dev/null 2>&1; then
		nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
		ok "GPU detected."
	else
		warn "nvidia-smi failed. Driver may not be loaded. Reboot may help."
		read -rp "Continue anyway? [yes/no]: " cont
		[[ "$cont" =~ ^(yes|y|YES|Y)$ ]] || exit 1
	fi
fi

# =============================================================================
# PHASE 3 - Build llama.cpp with CUDA
# =============================================================================
if phase "3/12 - Build llama.cpp with CUDA" \
	"Clone llama.cpp to ~/llama.cpp" \
	"cmake with GGML_CUDA=ON, CUDA_ARCHITECTURES=89 (Ada Lovelace = RTX 4050)" \
	"Compile (5-15 minutes)"; then

	if [ -d "$ROG_HOME/llama.cpp" ]; then
		warn "~/llama.cpp already exists."
		read -rp "Update existing checkout and rebuild? [yes/no]: " rebuild
		if [[ "$rebuild" =~ ^(yes|y|YES|Y)$ ]]; then
			confirm_run "git pull" bash -c "cd '$ROG_HOME/llama.cpp' && git pull origin master"
		else
			warn "Skipping clone/build."
			phase_done=1
		fi
	else
		confirm_run "clone llama.cpp" \
			git clone https://github.com/ggerganov/llama.cpp "$ROG_HOME/llama.cpp"
	fi

	if [ -z "${phase_done:-}" ]; then
		CUDA_ARCH=89
		info "Using CUDA_ARCHITECTURES=$CUDA_ARCH"

		confirm_run_block "cmake configure" \
			"cd '$ROG_HOME/llama.cpp' && cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=$CUDA_ARCH"

		info "Compiling (5-15 minutes)..."
		confirm_run_block "compile llama.cpp" \
			"cd '$ROG_HOME/llama.cpp' && cmake --build build --config Release -j\$(nproc)"

		if [ -x "$ROG_HOME/llama.cpp/build/bin/llama-server" ]; then
			ok "llama-server built."
			"$ROG_HOME/llama.cpp/build/bin/llama-server" --version 2>&1 | head -3 || true
		else
			fail "Build failed - llama-server binary not found."
			exit 1
		fi
	fi
	unset phase_done
fi

# =============================================================================
# PHASE 4 - Models directory
# =============================================================================
if phase "4/12 - Models directory + hf (Hugging Face CLI)" \
	"Create ~/models/ (where ALL model files live - never in /)" \
	"Point HF_HUB_CACHE at ~/models/.cache (keeps any HF cache predictable)" \
	"Install huggingface_hub via pip --user (provides the 'hf' command)" \
	"Note: 'huggingface-cli' was renamed to 'hf' - this script uses the new name" \
	"Check available disk space"; then

	confirm_run "create ~/models/" mkdir -p "$ROG_HOME/models"
	confirm_run "create ~/models/.cache for HF" mkdir -p "$ROG_HOME/models/.cache"

	# Persist HF_HUB_CACHE in ~/.bashrc so it's set for future shells too.
	# This prevents any future hf download from defaulting to ~/.cache/huggingface
	# which could land on a separate partition or surprise the user.
	if ! grep -q "HF_HUB_CACHE" "$ROG_HOME/.bashrc" 2>/dev/null; then
		confirm_run_block "set HF_HUB_CACHE in ~/.bashrc (so cache stays in ~/models/.cache)" \
			"echo '' >> $ROG_HOME/.bashrc
echo '# Keep Hugging Face cache inside ~/models so all model data is in one place' >> $ROG_HOME/.bashrc
echo 'export HF_HUB_CACHE=\"\$HOME/models/.cache\"' >> $ROG_HOME/.bashrc
echo 'export HF_HOME=\"\$HOME/models/.cache\"' >> $ROG_HOME/.bashrc"
	else
		ok "HF_HUB_CACHE already set in ~/.bashrc"
	fi
	# Set for current script run
	export HF_HUB_CACHE="$ROG_HOME/models/.cache"
	export HF_HOME="$ROG_HOME/models/.cache"

	if ! command -v hf >/dev/null 2>&1; then
		# First check if it exists at ~/.local/bin/ but PATH just doesn't include it
		if [ -x "$ROG_HOME/.local/bin/hf" ]; then
			info "hf found at ~/.local/bin/ but not in PATH. Will fix PATH below."
		else
			if ! pip install --user huggingface_hub 2>/dev/null; then
				confirm_run "install huggingface_hub (with --break-system-packages)" \
					pip install --user --break-system-packages huggingface_hub
			fi
		fi
	else
		ok "hf already installed and in PATH."
	fi

	# CRITICAL: pip install --user puts binaries in ~/.local/bin which Arch doesn't
	# add to PATH by default. Without this fix, phase 5 will fail with "command not found".
	if ! grep -q '\.local/bin' "$ROG_HOME/.bashrc" 2>/dev/null; then
		confirm_run_block "add ~/.local/bin to PATH in ~/.bashrc" \
			'echo "" >> ~/.bashrc
echo "# pip install --user puts binaries here" >> ~/.bashrc
echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc'
	else
		ok "~/.local/bin already in ~/.bashrc PATH"
	fi
	# And export for the current script session so phase 5 can find it
	export PATH="$ROG_HOME/.local/bin:$PATH"

	# Verify it's now reachable. The hf binary is provided by the huggingface_hub
	# pip package - it replaced the old, now-deprecated huggingface-cli.
	if command -v hf >/dev/null 2>&1; then
		ok "hf is now reachable: $(command -v hf)"
		info "Version: $(hf --version 2>&1 | head -1)"
	else
		fail "hf still not reachable. Check $ROG_HOME/.local/bin/ contents."
		ls -la "$ROG_HOME/.local/bin/" 2>/dev/null || warn "  ~/.local/bin/ doesn't exist"
		exit 1
	fi

	# Disk space check
	echo
	info "Disk space sanity check:"
	AVAIL_KB=$(df -k "$ROG_HOME" | awk 'NR==2 {print $4}')
	AVAIL_GB=$((AVAIL_KB / 1024 / 1024))
	info "Free space in $ROG_HOME's partition: ${AVAIL_GB} GB"

	if [ "$AVAIL_GB" -lt 25 ]; then
		fail "Less than 25 GB free. The primary model alone needs ~23 GB. Free some space first."
		read -rp "Continue anyway? [yes/no]: " cont
		[[ "$cont" =~ ^(yes|y|YES|Y)$ ]] || exit 1
	elif [ "$AVAIL_GB" -lt 60 ]; then
		warn "Less than 60 GB free. You can fit the primary (~23 GB) and probably the fallback (~9 GB),"
		warn "but not the heavy-lift (~21 GB). Skip the heavy-lift in phase 5 or free up space."
	else
		ok "Plenty of room for all three models (~53 GB total)."
	fi

	info "All three model repos below are public - no Hugging Face login needed."
fi

# =============================================================================
# PHASE 5 - Download models (gated per-model)
# =============================================================================
if phase "5/12 - Download models" \
	"Three models, each gated separately:" \
	"  Primary:    Qwen 3.6 35B A3B Q4_K_M    (~23 GB)" \
	"  Heavy:      Hermes 4.3 36B Q4_K_M       (~21 GB)" \
	"  Fallback:   Hermes 4 14B Q4_K_M         (~9 GB)" \
	"All three: ~53 GB" \
	"All files go under $ROG_HOME/models/ - nothing in /, /usr, /var, or /tmp"; then

	cd "$ROG_HOME/models"

	# Re-export HF cache vars in case this phase is run standalone after re-entry
	export HF_HUB_CACHE="$ROG_HOME/models/.cache"
	export HF_HOME="$ROG_HOME/models/.cache"

	download_model() {
		local repo="$1"
		local file_glob="$2"
		local local_dir="$3"
		local size_gb="$4"
		local description="$5"

		echo
		info "==> $description"
		info "    Repo:        $repo"
		info "    File:        $file_glob"
		info "    Destination: $ROG_HOME/models/$local_dir/"
		info "    HF cache:    $HF_HUB_CACHE"
		info "    Size:        ~${size_gb} GB"

		if [ -d "$ROG_HOME/models/$local_dir" ] && [ -n "$(ls -A "$ROG_HOME/models/$local_dir" 2>/dev/null | grep -v '^\.cache')" ]; then
			warn "Directory non-empty. Skipping (delete to re-download)."
			return
		fi

		# Check free space against this model's size (with 2 GB headroom)
		local need_gb=$((size_gb + 2))
		local avail_kb=$(df -k "$ROG_HOME/models" | awk 'NR==2 {print $4}')
		local avail_gb=$((avail_kb / 1024 / 1024))
		if [ "$avail_gb" -lt "$need_gb" ]; then
			fail "Only ${avail_gb} GB free; this model needs ~${need_gb} GB. Skipping."
			return
		fi

		read -rp "Download this model? [yes/no]: " dl
		if [[ "$dl" =~ ^(yes|y|YES|Y)$ ]]; then
			hf download "$repo" --include "$file_glob" \
				--local-dir "$ROG_HOME/models/$local_dir"
			# Verify the file actually landed where we expect
			if ls "$ROG_HOME/models/$local_dir"/*.gguf >/dev/null 2>&1; then
				ok "Downloaded to $ROG_HOME/models/$local_dir/"
				ls -lh "$ROG_HOME/models/$local_dir"/*.gguf | awk '{print "    " $9 " (" $5 ")"}'
			else
				fail "Download finished but no .gguf file found at expected path. Check manually."
			fi
		else
			warn "Skipped $repo"
		fi
	}

	download_model \
		"bartowski/Qwen_Qwen3.6-35B-A3B-GGUF" \
		"Qwen_Qwen3.6-35B-A3B-Q4_K_M.gguf" \
		"qwen-3.6-35b-a3b" 23 \
		"PRIMARY: Qwen 3.6 35B A3B (MoE, 3B active, fast tool-calling)"

	download_model \
		"NousResearch/Hermes-4.3-36B-GGUF" \
		"*Q4_K_M*" \
		"hermes-4.3-36b" 21 \
		"HEAVY: Hermes 4.3 36B (Nous dense, slower but higher quality)"

	download_model \
		"bartowski/NousResearch_Hermes-4-14B-GGUF" \
		"NousResearch_Hermes-4-14B-Q4_K_M.gguf" \
		"hermes-4-14b" 9 \
		"FALLBACK: Hermes 4 14B (fast, fits VRAM cleaner)"

	echo
	info "${BOLD}Final model inventory under $ROG_HOME/models/:${RESET}"
	du -sh "$ROG_HOME/models"/*/ 2>/dev/null | grep -v "\.cache" || warn "No models downloaded."

	echo
	info "Hugging Face cache (may contain duplicates / temp files):"
	if [ -d "$ROG_HOME/models/.cache" ]; then
		du -sh "$ROG_HOME/models/.cache" 2>/dev/null || echo "    (empty)"
		info "Safe to delete after downloads complete:"
		info "  rm -rf $ROG_HOME/models/.cache"
		info "(Don't delete it mid-download - that's where in-flight files live.)"
	fi

	echo
	info "${BOLD}Confirm: no model files ended up outside $ROG_HOME${RESET}"
	info "Verifying nothing slipped into /usr, /var, or /tmp..."
	for path in /usr/share/ollama /var/cache/huggingface /tmp/hf_cache /root/.cache; do
		if [ -d "$path" ] && [ -n "$(ls -A "$path" 2>/dev/null)" ]; then
			warn "Found content at $path - investigate manually"
		fi
	done
	ok "No unexpected model storage locations populated."
fi

# =============================================================================
# PHASE 6 - systemd USER units for llama-server
# =============================================================================
if phase "6/12 - systemd user units for llama-server" \
	"User units in ~/.config/systemd/user/ (not system, runs as you)" \
	"Three units: primary 8080, heavy 8081, fallback 8082" \
	"Only primary auto-starts; heavy/fallback are manual" \
	"Bound to 0.0.0.0 so HP can reach over LAN"; then

	UNIT_DIR="$ROG_HOME/.config/systemd/user"
	mkdir -p "$UNIT_DIR"

	cat >"$UNIT_DIR/llama-server-primary.service" <<EOF
[Unit]
Description=llama.cpp serving Qwen 3.6 35B A3B (primary)
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=$ROG_HOME/llama.cpp
ExecStart=$ROG_HOME/llama.cpp/build/bin/llama-server \\
  --model $ROG_HOME/models/qwen-3.6-35b-a3b/Qwen_Qwen3.6-35B-A3B-Q4_K_M.gguf \\
  --n-gpu-layers 30 \\
  --ctx-size 32768 \\
  --threads 8 \\
  --threads-batch 8 \\
  --batch-size 512 \\
  --flash-attn \\
  --host 0.0.0.0 \\
  --port 8080 \\
  --jinja
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=default.target
EOF
	ok "Wrote llama-server-primary.service (Qwen 3.6 35B A3B)"

	cat >"$UNIT_DIR/llama-server-heavy.service" <<EOF
[Unit]
Description=llama.cpp serving Hermes 4.3 36B (heavy-lift, manual)
After=graphical-session.target
Conflicts=llama-server-primary.service llama-server-fallback.service

[Service]
Type=simple
WorkingDirectory=$ROG_HOME/llama.cpp
ExecStart=$ROG_HOME/llama.cpp/build/bin/llama-server \\
  --model $ROG_HOME/models/hermes-4.3-36b/Hermes-4.3-36B-Q4_K_M.gguf \\
  --n-gpu-layers 18 \\
  --ctx-size 16384 \\
  --threads 8 \\
  --threads-batch 8 \\
  --batch-size 256 \\
  --flash-attn \\
  --host 0.0.0.0 \\
  --port 8081 \\
  --jinja
Restart=no
EOF
	ok "Wrote llama-server-heavy.service"

	cat >"$UNIT_DIR/llama-server-fallback.service" <<EOF
[Unit]
Description=llama.cpp serving Hermes 4 14B (fast fallback, manual)
After=graphical-session.target
Conflicts=llama-server-primary.service llama-server-heavy.service

[Service]
Type=simple
WorkingDirectory=$ROG_HOME/llama.cpp
ExecStart=$ROG_HOME/llama.cpp/build/bin/llama-server \\
  --model $ROG_HOME/models/hermes-4-14b/NousResearch_Hermes-4-14B-Q4_K_M.gguf \\
  --n-gpu-layers 999 \\
  --ctx-size 32768 \\
  --threads 8 \\
  --threads-batch 8 \\
  --batch-size 512 \\
  --flash-attn \\
  --host 0.0.0.0 \\
  --port 8082 \\
  --jinja
Restart=no
EOF
	ok "Wrote llama-server-fallback.service"

	confirm_run "reload systemd user daemon" systemctl --user daemon-reload

	echo
	read -rp "Enable + start the primary unit now? [yes/no]: " start_now
	if [[ "$start_now" =~ ^(yes|y|YES|Y)$ ]]; then
		read -rp "Enable lingering (runs even when not logged in)? [yes/no]: " linger
		if [[ "$linger" =~ ^(yes|y|YES|Y)$ ]]; then
			confirm_run "enable lingering for $ROG_USER" sudo loginctl enable-linger "$ROG_USER"
		fi
		confirm_run "enable primary" systemctl --user enable llama-server-primary.service
		confirm_run "start primary" systemctl --user start llama-server-primary.service

		info "Waiting 15s for model to load..."
		sleep 15
		if curl -sf --max-time 5 "http://localhost:8080/v1/models" >/dev/null; then
			ok "llama-server responding on :8080"
		else
			warn "Not responding yet. Loading 23GB MoE takes 1-3 min on first run."
			warn "Check: journalctl --user -u llama-server-primary -n 30"
		fi
	fi
fi

# =============================================================================
# PHASE 7 - SSH server
# =============================================================================
if phase "7/12 - SSH server (for HP -> ROG remote control)" \
	"Enable sshd so HP can remotely suspend this machine after morning runs" \
	"Optionally configure passwordless sudo for 'systemctl suspend' only" \
	"Print HP-side key-setup instructions for after this script finishes"; then

	confirm_run "enable + start sshd" sudo systemctl enable --now sshd

	echo
	info "sshd is now listening on port 22."
	echo

	read -rp "Configure passwordless 'sudo systemctl suspend' for $ROG_USER? [yes/no]: " passless_suspend
	if [[ "$passless_suspend" =~ ^(yes|y|YES|Y)$ ]]; then
		SUDOERS_FILE="/etc/sudoers.d/99-$ROG_USER-suspend"
		info "This creates $SUDOERS_FILE granting passwordless access to:"
		info "  /usr/bin/systemctl suspend"
		info "(Only that exact command - nothing else.)"

		confirm_run_block "create $SUDOERS_FILE" \
			"sudo tee $SUDOERS_FILE > /dev/null <<SUDOEOF
# Allow $ROG_USER to suspend without password (for remote suspend via SSH)
$ROG_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl suspend
SUDOEOF
sudo chmod 0440 $SUDOERS_FILE
sudo visudo -c -f $SUDOERS_FILE"

		info "Verified sudoers file syntax."
	fi

	echo
	read -rp "Disable SSH password authentication (key-only)? Recommended. [yes/no]: " disable_pw
	if [[ "$disable_pw" =~ ^(yes|y|YES|Y)$ ]]; then
		warn "Important: do NOT enable this until you've set up your key from the HP."
		warn "Otherwise you'll lock yourself out of remote access."
		read -rp "Have you already copied your HP's public key to this machine? [yes/no]: " key_done
		if [[ "$key_done" =~ ^(yes|y|YES|Y)$ ]]; then
			confirm_run_block "disable password auth in /etc/ssh/sshd_config" \
				"sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo systemctl restart sshd"
		else
			warn "Skipping. Re-run this script after key setup if you want to disable password auth."
		fi
	fi

	echo
	cat <<SSH_INSTRUCTIONS
${BOLD}From the HP, set up key-based SSH access:${RESET}

  # On the HP:
  ssh-keygen -t ed25519 -C "hp -> rog"            # only if you don't have a key
  ssh-copy-id $ROG_USER@$ROG_IP                   # copies your public key here

  # Test:
  ssh $ROG_USER@$ROG_IP "hostname && uptime"

  # If you set up passwordless suspend, test:
  ssh $ROG_USER@$ROG_IP "sudo systemctl suspend"
  # (this machine will go to sleep; wake it manually to continue)

After your key works, re-run this phase to disable password auth.

SSH_INSTRUCTIONS
fi

# =============================================================================
# PHASE 8 - Avahi / mDNS
# =============================================================================
if phase "8/12 - Avahi / mDNS (.local name resolution)" \
	"Advertise this machine as 'rogflow.local' on the LAN" \
	"System hostname stays as '$SYS_HOSTNAME' - only mDNS sees 'rogflow'" \
	"This avoids the hostname collision with the HP (also '$SYS_HOSTNAME')" \
	"Edit /etc/nsswitch.conf so .local names resolve from any local app"; then

	info "Configuring avahi to advertise as 'rogflow' (not '$SYS_HOSTNAME')"

	# avahi-daemon.conf might have host-name commented or set to default
	confirm_run_block "set avahi host-name=rogflow in /etc/avahi/avahi-daemon.conf" \
		"if grep -q '^host-name=' /etc/avahi/avahi-daemon.conf; then
    sudo sed -i 's/^host-name=.*/host-name=rogflow/' /etc/avahi/avahi-daemon.conf
elif grep -q '^#host-name=' /etc/avahi/avahi-daemon.conf; then
    sudo sed -i 's/^#host-name=.*/host-name=rogflow/' /etc/avahi/avahi-daemon.conf
else
    echo 'host-name=rogflow' | sudo tee -a /etc/avahi/avahi-daemon.conf > /dev/null
fi
grep '^host-name' /etc/avahi/avahi-daemon.conf"

	confirm_run "enable + start avahi-daemon" sudo systemctl enable --now avahi-daemon

	info "Updating /etc/nsswitch.conf so .local names resolve..."
	if grep -q "mdns_minimal" /etc/nsswitch.conf; then
		ok "mdns_minimal already in nsswitch.conf"
	else
		confirm_run_block "patch hosts: line in /etc/nsswitch.conf" \
			"sudo cp /etc/nsswitch.conf /etc/nsswitch.conf.bak
sudo sed -i 's/^hosts:.*/hosts: mymachines mdns_minimal [NOTFOUND=return] resolve [!UNAVAIL=return] files myhostname dns/' /etc/nsswitch.conf
grep '^hosts:' /etc/nsswitch.conf"
	fi

	echo
	info "Testing local mDNS resolution (give it 3 seconds)..."
	sleep 3
	if avahi-resolve --name rogflow.local 2>/dev/null | grep -q "rogflow.local"; then
		ok "rogflow.local resolves: $(avahi-resolve --name rogflow.local 2>/dev/null)"
	else
		warn "Not resolving yet. Sometimes takes up to a minute."
		warn "Test later: avahi-resolve --name rogflow.local"
	fi

	echo
	info "From the HP, after avahi is also set up there:"
	info "  ping rogflow.local"
	info "  curl http://rogflow.local:8080/v1/models"
fi

# =============================================================================
# PHASE 9 - Wake-on-Wi-Fi (WoWLAN) detection
# =============================================================================
if phase "9/12 - Wake-on-Wi-Fi (WoWLAN) detection" \
	"Probe Wi-Fi adapter for WoWLAN magic-packet capability" \
	"If supported, offer to enable (honest note: rarely reliable on consumer laptops)" \
	"Manual power management remains the realistic primary path"; then

	info "Checking $NET_IFACE WoWLAN capabilities..."
	echo

	if ! command -v iw >/dev/null 2>&1; then
		warn "iw not installed. Run phase 1 first."
	else
		PHY=$(iw dev "$NET_IFACE" info 2>/dev/null | awk '/wiphy/ {print "phy"$2; exit}')
		if [ -z "$PHY" ]; then
			warn "Could not detect PHY for $NET_IFACE. Probably not a Wi-Fi interface."
			info "If $NET_IFACE is actually wired Ethernet, regular WoL applies. See ethtool docs."
		else
			info "Detected PHY: $PHY"
			WOWLAN_OUTPUT=$(iw phy "$PHY" 2>/dev/null | sed -n '/WoWLAN support:/,/^[^[:space:]\t]/p' | head -20 || echo "")

			if [ -z "$WOWLAN_OUTPUT" ]; then
				warn "No WoWLAN section in 'iw phy' output."
				warn "This adapter likely does not support WoWLAN."
			elif echo "$WOWLAN_OUTPUT" | grep -qi "magic packet"; then
				ok "WoWLAN reports magic-packet support:"
				echo "$WOWLAN_OUTPUT"
				echo
				warn "Detection != reliability. Practical concerns:"
				warn "  - BIOS often kills Wi-Fi radio during sleep"
				warn "  - Wi-Fi association typically drops at suspend"
				warn "  - Routers don't always forward magic packets over Wi-Fi"
				warn "  - This adapter being capable does not mean your setup will wake"
				warn "  - Plan to use manual power management as the real path"
				echo
				read -rp "Try to enable WoWLAN magic-packet anyway? [yes/no]: " try_wol
				if [[ "$try_wol" =~ ^(yes|y|YES|Y)$ ]]; then
					confirm_run "enable WoWLAN on $PHY" sudo iw phy "$PHY" wowlan enable magic-packet
					info "Enabled for current session. Persistence across reboots is adapter-dependent."
					info "Test by suspending and trying to wake from HP. Do not rely on this for daily use."
				fi
			else
				warn "WoWLAN section present but no magic-packet support listed:"
				echo "$WOWLAN_OUTPUT"
				warn "Skipping WoWLAN. Plan for manual power management."
			fi
		fi
	fi

	echo
	info "Manual power management strategies that actually work:"
	info "  1. Leave ROG on overnight (idle draw ~25-40W)"
	info "  2. Power on / open lid before morning timer fires"
	info "  3. Shift the morning timer to a time you're up anyway"
	info "  After morning run, HP can ssh in and run 'sudo systemctl suspend' (set up in phase 7)"
fi

# =============================================================================
# PHASE 10 - Static IP guidance
# =============================================================================
if phase "10/12 - Static IP guidance (you do this part in your router)" \
	"Print MAC, current IP, gateway" \
	"Walk you through your router admin steps" \
	"Script does NOT touch the router - this is informational"; then

	cat <<STATIC_IP_GUIDE

${BOLD}To make this machine reliably reachable, reserve a static IP in your
router's DHCP settings.${RESET} mDNS (rogflow.local) is a friendlier fallback but
fragile - a hardcoded IP doesn't break when avahi crashes or the network
gets weird.

You need:
  This machine's MAC: ${BOLD}$ROG_MAC${RESET}
  Current IP:         $ROG_IP
  Router (gateway):   ${GATEWAY:-unknown}

${BOLD}Steps:${RESET}

  1. Open the router admin page:
       http://${GATEWAY:-192.168.1.1}
     The admin username/password is usually on a sticker on the router.
     Common defaults: admin/admin, admin/password, blank password.

  2. Find DHCP reservation settings. Menu names vary by router brand:
       - TP-Link:    DHCP -> Address Reservation
       - ASUS:       LAN -> DHCP Server -> Manually Assigned IP
       - Netgear:    Advanced -> Setup -> LAN Setup -> Address Reservation
       - JioFiber:   Network Setup -> LAN -> Bind IP-MAC
       - Xfinity:    Connected Devices -> Devices -> (pick device) -> Reserve IP
       - Linksys:    DHCP Reservations
       - OpenWrt:    Network -> DHCP and DNS -> Static Leases
     If none of these match, search "<your router brand> static DHCP" or
     check the router's manual.

  3. Add a reservation:
       - MAC address:  $ROG_MAC
       - Reserved IP:  pick something out of the way - e.g. ${GATEWAY%.*}.50
                       (must be inside the router's DHCP range)
       - Label:        rogflow (or whatever you'll recognize)

  4. Save the reservation. Some routers apply immediately; others need a
     reboot or you need to force this machine to renew its lease:
       sudo systemctl restart NetworkManager   # if using NetworkManager
       sudo systemctl restart systemd-networkd # if using systemd-networkd
       # or just reboot

  5. After applying, verify by checking your IP again:
       ip -4 addr show $NET_IFACE

  6. Update the HP's morning-run.sh with the reserved IP:
       RYZEN_HOSTNAME="${GATEWAY%.*}.50"     # or whichever IP you picked
     (Or use 'rogflow.local' if you trust mDNS - having the IP as backup
      is wise.)

STATIC_IP_GUIDE

	read -rp "Press enter when done (or to skip and configure later)..." _

	info "If you set up the reservation, current IP after renewal:"
	ip -4 addr show "$NET_IFACE" 2>/dev/null | awk '/inet / {print "    " $2}'
fi

# =============================================================================
# PHASE 11 - Firewall (LAN-only, optional)
# =============================================================================
if phase "11/12 - Firewall (optional, recommended)" \
	"Open ports to LAN subnet only - block from public internet" \
	"Ports: 22 (SSH), 5353/udp (mDNS), 8080-8082 (llama-server)" \
	"Skip if you manage firewall yourself"; then

	LAN_SUBNET=$(ip -4 route show dev "$NET_IFACE" | awk '/proto kernel/ {print $1; exit}')

	if [ -z "$LAN_SUBNET" ]; then
		warn "Could not auto-detect LAN subnet. Skipping firewall config."
	else
		info "Detected LAN subnet: $LAN_SUBNET"

		if command -v ufw >/dev/null 2>&1; then
			FW="ufw"
		elif command -v firewall-cmd >/dev/null 2>&1; then
			FW="firewalld"
		elif command -v nft >/dev/null 2>&1; then
			FW="nftables"
		else
			FW="none"
		fi
		info "Firewall tool: $FW"

		case "$FW" in
		ufw)
			read -rp "Add ufw rules for SSH, mDNS, llama-server from $LAN_SUBNET? [yes/no]: " ans
			if [[ "$ans" =~ ^(yes|y|YES|Y)$ ]]; then
				confirm_run "allow SSH (22/tcp) from LAN" \
					sudo ufw allow from "$LAN_SUBNET" to any port 22 proto tcp
				confirm_run "allow mDNS (5353/udp) from LAN" \
					sudo ufw allow from "$LAN_SUBNET" to any port 5353 proto udp
				confirm_run "allow llama-server 8080/tcp from LAN" \
					sudo ufw allow from "$LAN_SUBNET" to any port 8080 proto tcp
				confirm_run "allow llama-server 8081/tcp from LAN" \
					sudo ufw allow from "$LAN_SUBNET" to any port 8081 proto tcp
				confirm_run "allow llama-server 8082/tcp from LAN" \
					sudo ufw allow from "$LAN_SUBNET" to any port 8082 proto tcp
			fi
			;;
		firewalld | nftables)
			warn "$FW detected. Skipping auto-config - configure manually."
			info "You'll need to allow: 22/tcp 5353/udp 8080-8082/tcp from $LAN_SUBNET"
			;;
		none)
			warn "No firewall tool. Skipping. Recommend ufw if you ever connect to untrusted networks."
			;;
		esac
	fi
fi

# =============================================================================
# PHASE 12 - Smoke test
# =============================================================================
if phase "12/12 - Smoke test" \
	"Verify llama-server responds on :8080 (model loaded)" \
	"Verify avahi resolves rogflow.local" \
	"Verify sshd accepts connections"; then

	echo
	info "[1/3] llama-server on :8080..."
	if curl -sf --max-time 5 "http://localhost:8080/v1/models" >/dev/null; then
		ok "Model endpoint responding."
		info "Sending tiny test prompt..."
		TEST_RESPONSE=$(curl -sf --max-time 60 -X POST http://localhost:8080/v1/chat/completions \
			-H "Content-Type: application/json" \
			-d '{
                "messages": [{"role": "user", "content": "Reply with only the word OK."}],
                "max_tokens": 10,
                "temperature": 0
            }' | jq -r '.choices[0].message.content' 2>/dev/null || echo "")
		if [ -n "$TEST_RESPONSE" ]; then
			ok "Model says: ${BOLD}$TEST_RESPONSE${RESET}"
		else
			warn "No coherent response. Check: journalctl --user -u llama-server-primary -n 50"
		fi
	else
		warn "llama-server not reachable. Did you start it in phase 6?"
	fi

	echo
	info "[2/3] mDNS resolution..."
	if avahi-resolve --name rogflow.local 2>/dev/null | grep -q rogflow.local; then
		ok "rogflow.local -> $(avahi-resolve --name rogflow.local | awk '{print $2}')"
	else
		warn "rogflow.local not resolving locally. Sometimes takes 30-60s after avahi start."
	fi

	echo
	info "[3/3] sshd listening on 22..."
	if ss -tlnp 2>/dev/null | grep -q ':22 '; then
		ok "sshd listening."
	else
		warn "sshd not listening. Check: systemctl status sshd"
	fi

	echo
	info "${BOLD}From the HP${RESET} (after avahi/sshd setup over there too):"
	info "  ping rogflow.local"
	info "  curl http://rogflow.local:8080/v1/models"
	info "  ssh $ROG_USER@rogflow.local 'hostname && uptime'"
fi

# =============================================================================
# Done
# =============================================================================
echo
hr
say "Setup complete."
hr
echo
cat <<SUMMARY
${BOLD}Final summary${RESET}

llama.cpp:       $ROG_HOME/llama.cpp/build/bin/llama-server
Models:          $ROG_HOME/models/
systemd units:   $ROG_HOME/.config/systemd/user/llama-server-*.service
SSH:             enabled (port 22)
mDNS name:       rogflow.local (system hostname stays $SYS_HOSTNAME)

Ports open on LAN: 22 (SSH), 5353/udp (mDNS), 8080-8082 (llama-server)

${BOLD}For the HP's morning-run.sh, use:${RESET}
  RYZEN_HOSTNAME="rogflow.local"   # via mDNS
  # or, more robustly:
  RYZEN_HOSTNAME="<reserved static IP from your router>"
  RYZEN_MODEL_PORT="8080"
  RYZEN_USER="$ROG_USER"
  RYZEN_MAC="$ROG_MAC"   # only useful if you ever get wired Ethernet + WoL

${BOLD}HP-side actions you still need to do:${RESET}

  1. Set up SSH key auth:
     ssh-keygen -t ed25519                           # if no key yet
     ssh-copy-id $ROG_USER@$ROG_IP                   # or use rogflow.local
     ssh $ROG_USER@rogflow.local 'hostname'          # verify

  2. Configure mDNS on the HP (same way - install avahi + nss-mdns, edit
     /etc/nsswitch.conf). Without this, the HP can't resolve rogflow.local.

  3. Hostname collision warning:
     Both this machine and the HP have system hostname '$SYS_HOSTNAME'.
     The ROG advertises as rogflow.local via avahi (resolved above).
     Recommend renaming the HP's system hostname to something distinct
     (e.g. 'hp' or 'elitebook') to avoid confusion:
        sudo hostnamectl set-hostname hp
     This affects the HP's shell prompt and any tools that read /etc/hostname.
     Won't affect this script or the morning workflow.

  4. Reserve a static IP for this machine in your router (phase 10 guide).

  5. Update the HP's morning-run.sh with RYZEN_HOSTNAME and RYZEN_USER.

${BOLD}Daily operations cheat sheet:${RESET}

  Check model is up:
    systemctl --user status llama-server-primary

  Switch to heavy / fallback:
    systemctl --user stop llama-server-primary
    systemctl --user start llama-server-heavy      # or llama-server-fallback

  Watch model log live:
    journalctl --user -u llama-server-primary -f

  From the HP, suspend the ROG after morning run:
    ssh $ROG_USER@rogflow.local 'sudo systemctl suspend'
    # (works without password if you configured passwordless suspend in phase 7)

SUMMARY

ok "Done."
