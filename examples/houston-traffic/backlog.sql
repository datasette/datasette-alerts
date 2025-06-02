
.load uv:sqlite-gitoxide

create table version as 
select *,
  git_at(repo, commit_id, 'data.json') as data_json
from git_log('getIncidentsGit')
limit 1000;