Standard Java 20 Spring Boot REST API: <https://github.com/lavantien/springboot-restapi>  
Guide to Modern Software Engineering: <https://gist.github.com/lavantien/dc730dad7d7e8157000ddae845eddfd7>  
Physical & Mental Health Maintenance Guide: <https://gist.github.com/lavantien/b158252fcdaa6ba114e61d014212f349>  

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


