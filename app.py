#####
from flask import Flask, render_template, url_for, request, redirect
from flask_sqlalchemy import SQLAlchemy

from datetime import datetime
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import ForeignKey, delete, desc
from sqlalchemy import Integer
from sqlalchemy import func,select



#initialize app/db
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
db = SQLAlchemy(app)
is_first_game=True
game_ongoing=False

POSITION_ATTRIBUTES = {
        0: 'position',
        1: 'position_in_team',
        2: 'position_in_team',
        3: 'position_sitting_out'
    }


class Players(db.Model):
    __tablename__ = "players"
    id = db.Column(Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), nullable=False)

    consec_games = db.Column(db.Integer, default=0)
    current_team = db.Column(db.Integer, default=0) # 0 = in queue, 1 = team1, 2 = team2, 3 = sitting out
    position = db.Column(db.Integer, unique = True, default = -1) 
    
    first_game = db.Column(db.Boolean, default=True)
    game_ongoing = db.Column(db.Boolean, default=False)
    position = db.Column(db.Integer, default = 1)

    position_in_team = db.Column(db.Integer, default = -1)
    position_sitting_out = db.Column(db.Integer, default = -1)
    
    old_team = db.Column(db.Integer, default=-1)
    subbing_in = db.Column(db.Integer, default=False)
    def __repr__(self):
        return '<Player %r>' % self.id

#create the db. Check why this works later.
with app.app_context():
        db.create_all()



#subtracts the given offset from the position of every player in queue
def update_queue(offset):
    players = Players.query.order_by(Players.position).all()
    queue = [player for player in players if player.current_team == 0]
    for player in queue:
        player.position-=offset
        db.session.commit()


def num_in_queue():
    players = Players.query.order_by(Players.position).all()
    if players:
        return db.session.query(func.count(Players.id)).filter(Players.current_team == 0).scalar()
    else:
        return 0

def num_in_sitting_out():
    players = Players.query.order_by(Players.position).all()
    if players:
        return db.session.query(func.count(Players.id)).filter(Players.current_team == 1).scalar()
    else:
        return 0

#given a player, put them back in queue and update their position accordingly
def put_back_in_queue(player):

    max_position= num_in_queue()
    player.current_team=0
    player.position= max_position+1
    db.session.commit()
    return
# Helper function for remove_player and cancel_sit_out. Given a target player, shift the position of anyone on the target's current team 
# with a position higher than target player by the offset. 
def shift_by_player(target_player, offset=-1):
    cur_team = target_player.current_team
    position_attr = POSITION_ATTRIBUTES[cur_team]
    players = Players.query.order_by(Players.position).all()
    
    to_adjust = [player for player in players if player.current_team == cur_team and getattr(player, position_attr) > getattr(target_player, position_attr)]
    
    for player in to_adjust:
        setattr(player, position_attr, getattr(player, position_attr) + offset)
        db.session.commit()
#same as above, but takes in a team and the position to shift around.
def shift_by_position(cur_team, pos, offset=-1):
    position_attr = POSITION_ATTRIBUTES[cur_team]
    players = Players.query.order_by(Players.position).all()
    
    to_adjust = [player for player in players if player.current_team == cur_team and getattr(player, position_attr) > pos]
    
    for player in to_adjust:
        setattr(player, position_attr, getattr(player, position_attr) + offset)
        db.session.commit()
# Helper function for cancel_sit_out. Increases the position of anyone in queue by one.
def increment_all():
    
    players = Players.query.order_by(Players.position).all()
    queue = [player for player in players if player.current_team == 0]
    
    for player in queue:
        player.position+=1
        db.session.commit()

#Routes
@app.route('/')
def index():
    
    players = Players.query.order_by(Players.position).all()
    players_by_team_pos=Players.query.order_by(Players.position_in_team).all()
    players_by_sitting_out_pos = Players.query.order_by(Players.position_sitting_out).all()
    '''  
    queue = db.session.execute(db.select(players).where(players.current_team == 0))
    team1 = db.session.execute(db.select(players).where(players.current_team == 1))
    team2 = db.session.execute(db.select(players).where(players.current_team == 2))
    sitting_out = db.session.execute(db.select(players).where(players.current_team == 3))
    '''
    if players:
        queue = [player for player in players if player.current_team == 0]
        team1 = [player for player in players_by_team_pos if player.current_team == 1]
        team2 = [player for player in players_by_team_pos if player.current_team == 2]
        sitting_out = [player for player in players_by_sitting_out_pos if player.current_team == 3]
    else:
        queue = []
        team1 = []
        team2 = []
        sitting_out = []
    column_names = [c.name for c in Players.__table__.columns]
    num_in_team_1 = db.session.query(func.count(Players.id)).filter(Players.current_team == 1).scalar()
    num_in_team_2 = db.session.query(func.count(Players.id)).filter(Players.current_team == 2).scalar()

    num_joining = 10-num_in_team_1-num_in_team_2 

    sufficient_players= (num_joining > num_in_queue())
    return render_template('index.html', players=players, queue=queue, team1=team1,team2=team2, \
                        sitting_out=sitting_out,  is_first_game=is_first_game, game_ongoing=game_ongoing, \
                        column_names=column_names, getattr=getattr, sufficient_players=sufficient_players)


#possibly make a queu priority table that's linked with the main one?
@app.route('/remove_player', methods=["POST"])
def remove_player():
    player_id = request.form['name']
    target_player = db.get_or_404(Players, player_id, 
                           description=f"No user with id '{player_id}'."
                           )
    
    shift_by_player(target_player)
    db.session.delete(target_player)
    db.session.commit()
    return redirect(url_for('index'))


@app.route('/add_player', methods=['POST'])
def add_player():
    name =request.form['name']
    max_position = num_in_queue()
    
    new_player = Players(name = name, position =  max_position+1)

    db.session.add(new_player)
    db.session.commit()

    return redirect('/')

@app.route('/start_game', methods=['POST'])
def start_game():
     
    #max_position = db.session.query(func.count(Players.id)).filter(Players.current_team == 0).scalar()
    
    num_in_team_1 = db.session.query(func.count(Players.id)).filter(Players.current_team == 1).scalar()
    num_in_team_2 = db.session.query(func.count(Players.id)).filter(Players.current_team == 2).scalar()

    num_joining = 10-num_in_team_1-num_in_team_2 

    if num_joining > num_in_queue():
        print("insufficient players")

    print("num_in_team_1: " + str(num_in_team_1))
    while num_in_team_1 < 5:
        cur_player = db.session.query(Players).filter(Players.position == 1).first()
        

        cur_player.current_team = 1
        num_in_team_1 += 1
        cur_player.position=-1
        cur_player.position_in_team = num_in_team_1
        db.session.commit()
        update_queue(1)
        p2=db.session.query(Players).filter(Players.id==2).first()
        print("p2: "+p2.name +", position: "+str(p2.position))
        print(f"Added {cur_player.name} to team 1")
    
    print("num_in_team_2: " + str(num_in_team_2))
    while num_in_team_2 < 5:
        #one_or_404 is finding multiple results for some godforsaken reason, despite there clearly being no other results
        
        '''cur_player = db.session.execute(db.select(Players).where(Players.position == min_position)).scalars().all()
        for c in cur_player:
            print("Name: "+c.name)'''
        
        cur_player = db.session.query(Players).filter(Players.position == 1).first()
        print(f"Attempting to add {cur_player.name} to team 2")

        cur_player.current_team = 2

        num_in_team_2 += 1
        cur_player.position_in_team = num_in_team_2
        cur_player.position=-1
        db.session.commit()
        update_queue(1)
        print(f"Added {cur_player.name} to team 2")
        print("num_in_team_2: "+str(num_in_team_2))
    
    global game_ongoing
    game_ongoing=True
    return redirect(url_for('index'))




@app.route('/end_game', methods=['POST'])
def end_game():
    global game_ongoing
    players = Players.query.order_by(Players.position_in_team).all()
    sitting_out = [player for player in players if player.current_team == 3]
    
    #put anyone who was sitting out back onto their old team
    for p in sitting_out:
        print("sitting out player: "+p.name + ", old team: "+ str(p.old_team)+ ",  threshold: "+str(p.position_in_team-1))
        shift_by_position(p.old_team, p.position_in_team-1, 1)
        p.position_sitting_out = -1
        p.current_team=p.old_team
        db.session.commit()
    

    team1 = [player for player in players if player.current_team == 1]
    team2 = [player for player in players if player.current_team == 2]
    # if it's the first game, the winning team stays and the losing team goes back in queue
    global is_first_game
    if is_first_game:
        winner =int(request.form['winner'])
        if winner == 1:
            for player in team2:
                if player.subbing_in==False:
                    put_back_in_queue(player)
                
            for player in team1:
                player.consec_games += 1
                db.session.commit()
            
        else:
            for player in team1:
                if player.subbing_in==False:
                    put_back_in_queue(player)
                
            for player in team2:
                player.consec_games += 1
                db.session.commit()
    else: #otherwise, remove anyone who's played their 2 games.
        for team in team1, team2:
            # for both teams, if a player has played 2 games, reset consecutive games and put them back in queue.
            for player in team:
                if player.subbing_in==False:
                    
                    if player.consec_games == 1:
                        
                        put_back_in_queue(player)
                        player.consec_games=0
                        
                    else:
                        player.consec_games+=1    
                        db.session.commit()
    reversed_players=reversed(players)
    substitutes = [player for player in reversed_players if player.subbing_in]
    
    #put any subs back in the front of the queue
    for sub in substitutes:
        if sub.current_team==0:
            print("warning: already in queue")
        
        increment_all()
        
        sub.current_team=0
        sub.position=1
        sub.consec_games=0
        sub.subbing_in=False
        db.session.commit()

    is_first_game = False
    game_ongoing=False
    return redirect(url_for('index'))

@app.route('/sit_out', methods=["POST"])
def sit_out():
    player_id = request.form['name']

    target_player = db.get_or_404(Players, player_id, 
                           description=f"No user with id '{player_id}'.")
    
    shift_by_player(target_player)
    target_player.old_team=target_player.current_team
    target_player.current_team=3

    db.session.commit()
    
    #put target_player in sit_out queue
    players = Players.query.order_by(Players.position).all()
    #sit out priority =10*position_in_team + [number of people in sitting_out with the same team position]
    sit_out_range = [player for player in players if player.current_team == 0 and player.position_sitting_out>=target_player.current_team*10 and player.position_sitting_out<=(target_player.current_team-1)*10]
    target_player.position_sitting_out=10*target_player.position_in_team + len(sit_out_range)
    
    players = Players.query.order_by(Players.position).all()
    
    db.session.commit()

    #select a new player, and remove them from the queue
    first_in_queue=db.session.query(Players).filter(Players.position==1).first()
    shift_by_player(first_in_queue)

    #put them into the team
    first_in_queue.position=-1
    first_in_queue.current_team=target_player.old_team
    first_in_queue.position_in_team=5
    first_in_queue.subbing_in=True

    db.session.commit()
    return redirect(url_for('index'))



@app.route('/cancel_sit_out', methods=["POST"])
def cancel_sit_out():
    player_id = request.form['name']
    target_player = db.get_or_404(Players, player_id, 
                           description=f"No user with id '{player_id}'.")
    
    removed_player = Players.query.filter_by(current_team=target_player.old_team, position_in_team=5).first()
    shifted_player = Players.query.filter_by(current_team=target_player.old_team, position_in_team=target_player.position_in_team).first()

    #put the lowest priority person from target_player's team back in the front of the queue.
    increment_all()
    removed_player.current_team=0
    removed_player.position=1
    removed_player.subbing_in=False
    db.session.commit()

    #put target_player back on their team, increasing the positions of everyone else
    shift_by_player(shifted_player)
    shifted_player.position_in_team+=1

    target_player.current_team=target_player.old_team
    target_player.old_team=-1
    target_player.position_sitting_out=-1

    db.session.commit()
    
    return redirect(url_for('index'))

@app.route('/remove_all')
def remove_all():
    global is_first_game, game_ongoing
    is_first_game=True
    game_ongoing=False
    db.session.query(Players).delete()
    
    db.session.commit()  # Commit the changes to the database
    
    return redirect(url_for('index'))  # Redirect to the index page

@app.route('/populate_table', methods=['POST'])
def populate_table():
    num_players=int(request.form['number'])
    max_position = num_in_queue()
    print(f"max position at start: {max_position}")
    for i in range(1,num_players+1):
        name=f"P{str(i)}"

        new_player = Players(name = name, position =  max_position+1)
        max_position +=1
        db.session.add(new_player)
        db.session.commit()
    print(f"max position at end: {max_position}")
    return redirect('/')

def swap_attr(p1,p2, attrib):
    p1_placeholder=getattr(p1,attrib)
    setattr(p1, attrib, getattr(p2,attrib))
    setattr(p2, attrib, p1_placeholder)
    db.session.commit()
#given two players, swaps their current team, and active positions
@app.route('/swap_positions', methods=['POST'])
def swap_positions():
    p1_id=request.form['p1']
    p2_id=request.form['p2']
    p1 = db.get_or_404(Players, p1_id, 
                           description=f"No user with id '{p1_id}'."
                           )
    p2 = db.get_or_404(Players, p2_id, 
                           description=f"No user with id '{p2_id}'."
                           )
    p1_position_attr = POSITION_ATTRIBUTES[p1.current_team]
    p2_position_attr = POSITION_ATTRIBUTES[p2.current_team]
    
    if p1_position_attr==p2_position_attr:
        swap_attr(p1,p2, p1_position_attr)
    else:
        swap_attr(p1,p2, p1_position_attr)
        swap_attr(p1,p2, p2_position_attr)
    

    swap_attr(p1,p2,"current_team")
    swap_attr(p1,p2, "subbing_in")
    swap_attr(p1,p2, "old_team")
    return redirect('/')

@app.route("/rules")
def rules():
    return render_template('rules.html')

if __name__ == "__main__":

    app.run(debug=True)