require 'fileutils'

remote = "teapot@167.71.110.79"
remote_path = "/etc/nginx/sites-available/update.rethinkdb.com"
app_path = "/var/www/update.rethinkdb.com/"

desc 'Update the nginx configuration'
task :update_nginx do
    nginx_conf = "nginx.conf"
    sh "scp #{nginx_conf} #{remote}:/etc/nginx/sites-available/update.rethinkdb.com"
    sh "ssh #{remote} -t 'sudo service nginx restart'"
end

desc 'Use rsync to upload files to the update server'
task :publish, [:force] do |t, args|
    if args.force == "force"
      puts "Publishing to #{remote_path}."
      pretend = ''
    else
      puts "Not publishing to #{remote_path} (Dry-run, use publish[force] to do the actual upload)."
      pretend = "--dry-run"
    end

    src = 'update.rethinkdb.com'
    sh "rsync --progress --recursive --delete --compress --human-readable --rsh='ssh' --itemize-changes --delay-updates --copy-links #{pretend} #{src}/ #{remote}:#{remote_path}"

    if args.force == "force"
      puts "Published to #{remote_path}."
    else
      puts "Not published to #{remote_path} (Dry-run, use publish[force] to do the actual upload)."
    end

    if args.force == "force"
      sh "ssh #{remote} -t 'cd #{app_path} && ./update.sh'"
    end
end
