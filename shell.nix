{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python310

    # Required for numpy/pandas native extensions
    stdenv.cc.cc.lib
    zlib
  ];

  # Allow uv from outside nix-shell to work
  nativeBuildInputs = with pkgs; [
    # Include these so pip-installed packages can find headers/libs
    pkg-config
  ];

  shellHook = ''
    # Set LD_LIBRARY_PATH for native Python packages (numpy, pandas, etc.)
    export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib:${pkgs.zlib}/lib:''${LD_LIBRARY_PATH:-}"

    echo "NixOS dev shell loaded. LD_LIBRARY_PATH is set for numpy/pandas."
    echo "Run: uv run python manage.py test cities.tests"
  '';
}
