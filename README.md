# clitm — Command-line Temp Mail

<img src="https://raw.githubusercontent.com/SiddharthGuptaPyDev/clitm/refs/heads/main/img/clitm-banner-rounded.png" alt="clitm Banner" style="max-width: 100%; height: auto;"/>

`clitm` is a simple, efficient command-line tool that provides temporary email functionality directly from your terminal.  
It uses the [Mail.tm](https://mail.tm) API to create disposable email addresses, check messages, and manage temporary inboxes securely and quickly.

---

## Features

- Generate disposable email addresses instantly
- Read and manage temporary inbox messages
- Delete any inbox message
- Save any inbox message locally
- Dispose whole temp mail session after terminating
- Lightweight and dependency-minimal (Python 3 + Requests)
- Works across major Linux distributions
- Distributed via `.deb` and APT for easy installation

---

## Installation
Run this one-liner in terminal:
```bash
curl -L https://github.com/siddharthguptapydev/clitm/releases/latest/download/clitm_1.0.0-1_all.deb -o clitm.deb
sudo dpkg -i clitm.deb
sudo apt-get install -f
```
---

## Usage

Once installed, simply run:

```bash
clitm
```

### Command Options

| Command       | Description                            |
| ------------- | -------------------------------------- |
| `clitm`       | Launch the TempMail CLI interface      |
| `clitm -h`    | Show help and usage information        |
| `clitm -info` | Show developer and version information |

---

## Example
![Screenshot](https://i.ibb.co/tgTHPrZ/Screenshot-20251028-144726.png)
---

## Development

Clone the repository and install dependencies:

```bash
git clone https://github.com/siddharthguptapydev/clitm.git
cd clitm
pip install -r requirements.txt
```

### Build a Debian Package

```bash
debuild -us -uc
```

The resulting `.deb` file will be available in the parent directory.

### Test Installation

```bash
sudo dpkg -i ../clitm_1.0.0-1_all.deb
```

---

## Contributing

Contributions, feature requests, and bug reports are welcome.
Please open an issue or submit a pull request via GitHub.

---

## License

This project is licensed under the **MIT License**.
See the [LICENSE](LICENSE.md) file for details.

---

## Author

**Luminar |**
[GitHub](https://github.com/siddharthguptapydev) • [Email](mailto:siddharthguptaindianboy@gmail.com)

---

> *clitm — Temporary email, right from the command l$0
