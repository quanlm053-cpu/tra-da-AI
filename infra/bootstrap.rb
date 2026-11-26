# Only for the dedicated fresh Redmine instance created by compose.yaml.
require 'json'
require 'securerandom'
raise 'Refusing to modify an unrelated Redmine project' if Project.where.not(identifier: 'club-equipment-lending').exists?
states = {7=>['Backlog',false],8=>['Selected',false],9=>['Blocked',false],10=>['Code Review',false],11=>['Ready for Test',false],12=>['Testing',false],13=>['ToDo',false],14=>['In Review',false],15=>['Done',true]}
states.each do |id,(name,closed)|
  row=IssueStatus.find_by(id:id)
  raise "Status ID #{id} conflicts with existing data" if row && row.name!=name
  IssueStatus.create!(id:id,name:name,is_closed:closed,position:id) unless row
end
{4=>'Story',5=>'Task'}.each do |id,name|
  row=Tracker.find_by(id:id)
  raise "Tracker ID #{id} conflicts" if row && row.name!=name
  Tracker.create!(id:id,name:name,default_status_id:7,position:id) unless row
end
permissions=[:view_issues,:add_issues,:edit_issues,:add_issue_notes,:view_private_notes,:view_time_entries,:log_time,:view_files,:manage_files]
roles=%w[Developer Reporter BA BE FE TESTER].map do |name|
  role=Role.find_or_initialize_by(name:name)
  role.assignable=true
  role.permissions=permissions
  role.save!
  role
end
project=Project.find_by(identifier:'club-equipment-lending')
unless project
  raise 'Project ID 2 already in use' if Project.exists?(2)
  project=Project.create!(id:2,name:'Mượn thiết bị',identifier:'club-equipment-lending',is_public:false)
end
project.enabled_module_names=%w[issue_tracking time_tracking files]
project.tracker_ids=Tracker.pluck(:id)
roles.each do |role|
  [4,5,1].each do |tracker|
    IssueStatus.pluck(:id).each do |old_id|
      IssueStatus.pluck(:id).each do |new_id|
        next if old_id==new_id
        WorkflowTransition.find_or_create_by!(role_id:role.id,tracker_id:tracker,old_status_id:old_id,new_status_id:new_id)
      end
    end
  end
end
%w[PM SA BA BE FE DEVOPS REVIEW TESTER].each do |label|
  login='lending-ai-'+label.downcase
  user=User.find_by(login:login)
  unless user
    user=User.new(login:login,firstname:'Lending AI',lastname:label,mail:login+'@agents.trada.invalid',status:1)
    user.password=SecureRandom.hex(32)
    user.password_confirmation=user.password
    user.save!
  end
  member=Member.find_or_initialize_by(project_id:project.id,user_id:user.id)
  member.role_ids=[roles.first.id]
  member.save!
end
Setting.rest_api_enabled='1'
%w[issue_statuses trackers projects].each do |table|
  ActiveRecord::Base.connection.reset_pk_sequence!(table)
end
admin=User.find_by(login:'admin')
raise 'Default admin is missing' unless admin
credentials_path='/tmp/trada-credentials.json'
unless File.exist?(credentials_path)
  password=SecureRandom.hex(20)
  admin.password=password
  admin.password_confirmation=password
  admin.must_change_passwd=false
  admin.save!
  File.write(credentials_path,JSON.pretty_generate({redmine_api_key:admin.api_key,admin_login:'admin',admin_password:password}))
  File.chmod(0600,credentials_path)
end
puts 'Trà đá AI Redmine workspace is ready. Credentials remain in the private file.'
