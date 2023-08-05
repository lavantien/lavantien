I'm just a random programmer who loves to code

Genetic: <https://github.com/lavantien/genetic-cpp>  
Sudoku CLI: <https://github.com/lavantien/sudoku-cli>  
Standard Spring Boot REST API: <https://github.com/lavantien/springboot-restapi>  
Guide to Modern Software Engineering: <https://gist.github.com/lavantien/dc730dad7d7e8157000ddae845eddfd7>  
Physical & Mental Health Maintenance Guide: <https://gist.github.com/lavantien/b158252fcdaa6ba114e61d014212f349>  
Buddhism Research: <https://gist.github.com/lavantien/5789220c9f07c8b5e0b8728b4ac53df6>  
Chess, Rubiks, Games, and Languages Resources: <https://gist.github.com/lavantien/514f1c06eb3c4f643fe9085122ed8f6c>  

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


