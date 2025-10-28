from setuptools import setup, find_packages

setup(
    name="clitm",
    version="1.0.0",
    author="Luminar",
    author_email="siddharthguptaindianboy@gmail.com",
    description="Command-line TempMail client using Mail.tm",
    license="MIT",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=["requests"],
    entry_points={
        "console_scripts": [
            "clitm=clitm:cli",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    python_requires=">=3.8",
)
