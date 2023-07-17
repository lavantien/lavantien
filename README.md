I'm just a random programmer who love code

Genetic: <https://github.com/lavantien/genetic-cpp>  
Sudoku CLI: <https://github.com/lavantien/sudoku-cli>  
SumoBot: <https://github.com/lavantien/SumoBot>  
Gist Snippets: <https://gist.github.com/lavantien>  
Professional Programming Resources: <https://gist.github.com/lavantien/5c2d8aa3103ca32c1c817c36fd8d0fb1>  
Buddhism Research: <https://gist.github.com/lavantien/5789220c9f07c8b5e0b8728b4ac53df6>  
Résumé: <https://github.com/lavantien/resume>  

<details>
  <summary>show more</summary>

```bash
sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y && rustup update && brew upgrade
```

```bash
docker rm $(docker ps -a -q --filter "ancestor=${IMG_ID}")
```

```bash
gh repo list ${REPO_NAME} --limit 1000 | while read -r repo _; do
  gh repo clone "$repo" "$repo" -- -q 2>/dev/null || (
    cd "$repo" || exit
    git checkout -q main 2>/dev/null || true
    git checkout -q master 2>/dev/null || true
    git pull -q
  )
done
```

```vim
:'<,'>norm! @a
```

![](./profile-3d-contrib/profile-gitblock.svg)

</details>


