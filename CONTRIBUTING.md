# Contributing to Redfish Client SDK

Thank you for your interest in contributing! This project welcomes contributions and suggestions.

## Contributor License Agreement (CLA)

Most contributions require you to agree to a Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us the rights to use your contribution. For details, visit [https://cla.opensource.microsoft.com](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide a CLA and decorate the PR appropriately (e.g. status check, comment). Simply follow the instructions provided by the bot. You will only need to do this once across all repos using our CLA.

## Code of Conduct

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/). See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) for details, or contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with questions.

---

## How to Contribute

### Reporting Bugs

- Search [existing issues](../../issues) before opening a new one.
- Use the **Bug Report** issue template.
- Include the language SDK (Python / C++ / Rust), OS, and simulator version.

### Requesting Features

- Open a [Feature Request](../../issues/new?template=feature_request.md) issue first.
- New SDK operations must be implemented in **all three languages** or clearly scoped to one.

### Submitting a Pull Request

1. **Fork** the repository and create a branch from `main`.
2. **Follow the engineering discipline** documented in [README.md](README.md#contributing):
   - Requirements first — if it is not in `docs/requirements.md`, discuss it first
   - Design before code — update `docs/design/` if the implementation diverges
   - Tests required — all changes must include or update tests
3. **Run the test suite** for the language(s) you modified:

   ```bash
   # Python
   cd python && pip install -e ".[dev]" && pytest

   # C++
   cd cpp && cmake -B build && cmake --build build --parallel
   cd cpp/build && ctest

   # Rust
   cd rust && cargo test
   ```

4. **Run the samples** against the Redfish mockup simulator before submitting:

   ```bash
   # Start the simulator, then:
   python3 bench/run_bench.py --runs 3
   ```

5. **Keep the API surface consistent** across languages — Python is the reference implementation.
6. Open the PR against `main`. The CLA bot and CI checks must pass before review.

### Adding a New Language Binding

Follow the architecture in `docs/architecture/architecture-sdk.md`. The design doc must come first.

---

## Development Setup

See [README.md](README.md) for full build instructions per language. Quick summary:

| Language | Prerequisite | Build |
|---|---|---|
| Python | Python ≥ 3.10, pip | `cd python && pip install -e ".[dev]"` |
| C++ | cmake, libcurl, libssl, nlohmann-json | `cd cpp && cmake -B build && cmake --build build` |
| Rust | rustc ≥ 1.75, cargo | `cd rust && cargo build` |

## Questions

Open a [Discussion](../../discussions) rather than an issue for questions or design conversations.
