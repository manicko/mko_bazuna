1) У нас очень много накапливается файлов миграций, но мы в dev режиме и сохранение обратной совместимости нам не нужно. 
Поэтому, нужно наладить механизм работы такой, чтобы файлы миграций не копились, пока мы в dev
Можно какую-то инструкцию + скрипт, чтобы не в ручном режиме все делать.
Плюс сейчас ошибки в файлах миграции
2) Также, после выполнения планов c:\py_dev\mko_bazuna>docker

У нас ошибка, нужно разобраться что некорректно исправили и как исправить, учитывая нужную нам архитектуру

 compose --env-file .env.docker -f docker-compose.yml -f docker-compose.dev.override.yml up -d --force-recreate
[+] up 20/20
 ✔ Image postgres:18-alpine            Pulled                                                                     287.0s
 ✔ Network mko_bazuna_default          Created                                                                      0.1s
 ✔ Volume mko_bazuna_media_volume      Created                                                                      0.0s
 ✔ Volume mko_bazuna_postgres_data     Created                                                                      0.0s
 ✔ Container mko_bazuna-db-1           Healthy                                                                      8.0s
 ✘ Container mko_bazuna-migrate-1      Error service "migrate" didn't complete successfully: exit 1                14.3s
 ✔ Container mko_bazuna-web-1          Created                                                                      0.7s
 ✔ Container mko_bazuna-create_admin-1 Created                                                                      0.2s
 ✔ Container mko_bazuna-bot-1          Created                                                                      0.4s
service "migrate" didn't complete successfully: exit 1 Обрати внимание, мы в dev нам не нужно много файлов миграций - не нужна обратная совместимость, достаточно 1. 

