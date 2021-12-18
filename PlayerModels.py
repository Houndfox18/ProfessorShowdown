import numpy as np
import BattleUtilities
import GameNode

from poke_env.player.env_player import Gen8EnvSinglePlayer
from poke_env.player.random_player import RandomPlayer
from poke_env.player.player import Player

from GameNode import GameNode

class SelfBattler2(RandomPlayer):
    def embed_battle(self, battle):
        # -1 indicates that the move does not have a base power
        # or is not available
        moves_base_power = -np.ones(4)
        moves_dmg_multiplier = np.ones(4)
        for i, move in enumerate(battle.available_moves):
            moves_base_power[i] = (
                move.base_power / 100
            )  # Simple rescaling to facilitate learning
            if move.type:
                moves_dmg_multiplier[i] = move.type.damage_multiplier(
                    battle.opponent_active_pokemon.type_1,
                    battle.opponent_active_pokemon.type_2,
                )

        # We count how many pokemons have not fainted in each team
        remaining_mon_team = (
            len([mon for mon in battle.team.values() if mon.fainted]) / 6
        )
        remaining_mon_opponent = (
            len([mon for mon in battle.opponent_team.values() if mon.fainted]) / 6
        )

        # Final vector with 10 components
        return np.concatenate(
            [
                moves_base_power,
                moves_dmg_multiplier,
                [remaining_mon_team, remaining_mon_opponent],
            ]
        )

    def compute_reward(self, battle) -> float:
        return self.reward_computing_helper(
            battle, fainted_value=2, hp_value=1, victory_value=30
        )

class MaxDamagePlayer(RandomPlayer):
    def choose_move(self, battle):
        # If the player can attack, it will
        if battle.available_moves:
            # Finds the best move among available ones
            best_move = max(battle.available_moves, key=lambda move: move.base_power)
            return self.create_order(best_move)

        # If no attack is available, a random switch will be made
        else:
            return self.choose_random_move(battle)

class MinimaxPlayer(Player): 

    previous_action = None
    maxDepth = 1 
    # The nodes keep track of battle states, moves are transitions between states
    def choose_move(self, battle):
        # HP values for you and your opponent's Pokemon are a dictionary that maps Pokemon to HP
        current_hp = {}
        for pokemon in battle.team.values():
            current_hp.update({pokemon : pokemon.current_hp})
        opponent_hp = {}
        for pokemon in battle.opponent_team.values():
            opponent_hp.update({pokemon : pokemon.current_hp})
        starting_node = GameNode(battle, battle.active_pokemon, current_hp, battle.opponent_active_pokemon, opponent_hp, None, not battle.can_dynamax, battle.active_pokemon.is_dynamaxed, not battle.opponent_can_dynamax, battle.opponent_active_pokemon.is_dynamaxed, float('-inf'), None, self.previous_action)
        if battle.active_pokemon.current_hp <= 0: 
        #    print(f"Pokemon {battle.active_pokemon} fainted")
            self.pick_best_switch(starting_node, 0)
        else: 
            self.minimax(starting_node, 0, True)
        child_nodes = starting_node.children
        best_score = float('-inf')
        best_node = None
        for child in child_nodes:
            if child.score >= best_score: 
                best_score = child.score
                best_node = child
        if best_node == None: 
            #print(f"Best node is none for some reason! Length of child_nodes is {len(child_nodes)}")
            self.previous_action = None
            return self.choose_default_move(battle)
        #if isinstance(best_node.action, Pokemon): 
            #print(f"Switching from {battle.active_pokemon} (type matchup score {BattleUtilities.get_defensive_type_multiplier(battle.active_pokemon, battle.opponent_active_pokemon)}) to {best_node.action} (type matchup score {BattleUtilities.get_defensive_type_multiplier(best_node.action, battle.opponent_active_pokemon)}) against {battle.opponent_active_pokemon}")
        #else:
        #    print(f"Pokemon {battle.active_pokemon} attacking with {best_node.action} against {battle.opponent_active_pokemon}")
        self.previous_action = best_node.action
        return self.create_order(best_node.action)



    def minimax(self, node, depth, is_bot_turn):
        if depth == self.maxDepth or self.is_terminal(node): 
            self.score(node)
            return node.score
        if is_bot_turn:
            score = float('-inf')
            bot_moves = node.generate_bot_moves()
            for move in bot_moves: 
                child_score = self.minimax(move, depth, False)
                score = max(score, child_score)
                print
            node.score = score
            return score
        else: 
            score = float('inf')
            opponent_moves = node.generate_opponent_moves()
            if len(opponent_moves) > 0:
                for move in opponent_moves: 
                    child_score = self.minimax(move, depth + 1, True)
                    score = min(score, child_score)
            else: 
                score = float('-inf')
            node.score = score
            return score



    def pick_best_switch(self, node, depth): 
        switches = node.add_bot_switches()
        score = float('-inf')
        for switch in switches:
            child_score = self.minimax(switch, depth, False)
            score = max(score, child_score)
        node.score = score
        return score



    # This function determines if this is an end state and we should stop
    def is_terminal(self, node):
        all_fainted = True
        for pokemon in node.current_HP.keys(): 
            if node.current_HP[pokemon] > 0:
                all_fainted = False
        if all_fainted: 
            return True
        all_fainted = True
        for pokemon in node.opponent_HP.keys():
            if node.opponent_HP[pokemon]:
                all_fainted = False
        if all_fainted: 
            return True
        return False



    def score(self, node):
        score = 0
        # Get positive points for dealing damage and knocking out opponent
        for pokemon in node.opponent_HP.keys():
            if pokemon.current_hp is not None:
                if node.opponent_HP[pokemon] <= 0 and pokemon.current_hp > 0: 
                    score += 300
                else:
                    damage = pokemon.current_hp - node.opponent_HP[pokemon] 
                    score += 3 * damage
            #else: 
                #print(f"Pokemon is {pokemon}, HP is None")
        # Lose points for taking damage or getting knocked out
        for pokemon in node.current_HP.keys():
            if node.current_HP[pokemon] <= 0 and pokemon.current_hp > 0: 
                score -= 100
            else: 
                damage = (pokemon.current_hp / pokemon.max_hp) - (node.current_HP[pokemon] / pokemon.max_hp)
                score -= damage
        # Lose points for getting outsped by opponent
        #if BattleUtilities.opponent_can_outspeed(node.current_pokemon, node.opponent_pokemon):
        #    score -= 25
        # Add / Subtract points for type match-up
        #type_multiplier = BattleUtilities.get_defensive_type_multiplier(node.current_pokemon, node.opponent_pokemon)
        #if type_multiplier == 4: 
        #    score -= 50
        #if type_multiplier == 2: 
        #    score -= 25
        #if type_multiplier == 0.5:
        #    score += 25
        #if type_multiplier == 0.25:
        #    score += 50
        #if node.battle.can_dynamax and node.has_dynamaxed:
        #    score -= 25
        node.score = score
        return score

class SmartDamagePlayer(Player):
    prevDamagePercent = 100 
    currentdamagePercent = 100 
    usedMovePreviously = False 
    currentOpponent = None
    previousOpponent = None

    def choose_move(self, battle):
        self.currentOpponent = battle.opponent_active_pokemon
        if self.currentOpponent != self.previousOpponent: 
            self.currentDamagePercent = 100
            self.previousDamagePercent = 100
            # print(f"New opponent is {self.currentOpponent}")
        else: 
            self.currentDamagePercent = battle.opponent_active_pokemon.current_hp
        #    if self.usedMovePreviously: 
                # print(f'Actual damage % done was {(self.prevDamagePercent - self.currentDamagePercent)}, previous health % was {self.prevDamagePercent}, current health percentage is {self.currentDamagePercent}%')
        self.prevDamagePercent = self.currentDamagePercent
        self.usedMovePreviously = False
        self.previousOpponent = self.currentOpponent
        

        # If Pokemon is out of moves, switch to best option
        if not battle.available_moves: 
            best_switch = self.choose_best_switch(battle)
            if best_switch is None: 
                return self.choose_default_move(battle)
            return self.create_order(best_switch)
        
        # Use info such as type matchup and relative speed to determine who to switch to
        matchup_score = self.get_matchup_score(battle.active_pokemon, battle.opponent_active_pokemon)
        # If negative situation exceeds threshold, switch Pokemon
        if matchup_score >= 1:
            best_switch = self.choose_best_switch(battle)
            if best_switch is not None: 
                return self.create_order(best_switch)
        

        # finds the best move among available ones
        self.usedMovePreviously = True
        best_move = max(battle.available_moves, key=lambda move: BattleUtilities.calculate_damage(move, battle.active_pokemon, battle.opponent_active_pokemon, True, True))
        # print(f'Best move was {best_move}, Calculated damage value was {self.calculate_damage(best_move, battle)}')
        return self.create_order(best_move)

    def choose_best_switch(self, battle): 
        if not battle.available_switches: 
            return None
        # Go through each Pokemon that can be switched to, and choose one with the best type matchup
        # (smaller multipliers are better) 
        best_score = float('inf')
        best_switch = battle.available_switches[0] 
        for switch in battle.available_switches: 
            score = self.get_matchup_score(switch, battle.opponent_active_pokemon)
            if score < best_score: 
                best_score = score
                best_switch = switch
        return best_switch
    
    # Gets a number that determines how well the Pokemon matches up with opponent. Lower scores are better
    def get_matchup_score(self, my_pokemon, opponent_pokemon):
        score = 0
        defensive_multiplier = BattleUtilities.get_defensive_type_multiplier(my_pokemon, opponent_pokemon)
        # A multiplier greater than 1 means we are at a type disadvantage. If there is a better type match, switch
        if defensive_multiplier == 4:
            score += 1
        elif defensive_multiplier == 2:
            score += 0.5
        elif defensive_multiplier == 0.5:
            score -= 0.5
        elif defensive_multiplier == 0.25:
            score -= 1
        if BattleUtilities.opponent_can_outspeed(my_pokemon, opponent_pokemon):
            score += 0.5
        return score


class TrainedRLPlayer(Gen8EnvSinglePlayer):
    
    def __init__(self, model, *args, **kwargs):
        Gen8EnvSinglePlayer.__init__(self, *args, **kwargs)
        self.model = model
        self.model.summary()

    def embed_battle(self, battle):
        # -1 indicates that the move does not have a base power
        # or is not available
        moves_base_power = -np.ones(4)
        moves_dmg_multiplier = np.ones(4)
        for i, move in enumerate(battle.available_moves):
            moves_base_power[i] = (
                move.base_power / 100
            )  # Simple rescaling to facilitate learning

        # We count how many pokemons have not fainted in each team
        remaining_mon_team = (
            len([mon for mon in battle.team.values() if mon.fainted]) / 6
        )
        remaining_mon_opponent = (
            len([mon for mon in battle.opponent_team.values() if mon.fainted]) / 6
        )

        # Final vector with 10 components
        score = 0
        my_pokemon = battle.active_pokemon
        opponent_pokemon = battle.opponent_active_pokemon
        defensive_multiplier = BattleUtilities.get_defensive_type_multiplier(my_pokemon, opponent_pokemon)
        # A multiplier greater than 1 means we are at a type disadvantage. If there is a better type match, switch
        if defensive_multiplier == 4:
            score += 1
        elif defensive_multiplier == 2:
            score += 0.5
        elif defensive_multiplier == 0.5:
            score -= 0.5
        elif defensive_multiplier == 0.25:
            score -= 1
        if BattleUtilities.opponent_can_outspeed(my_pokemon, opponent_pokemon):
            score += 0.5
        score = np.array(score).reshape(-1)
        return np.concatenate(
            [
                moves_base_power,
                moves_dmg_multiplier,
                [remaining_mon_team, remaining_mon_opponent], score,
            ]
        )

    def choose_move(self, battle):
        if self.model is None:
            return super().choose_move(battle)

        embeded = self.embed_battle(battle)
        prediction = self.model.predict(np.expand_dims([embeded], 0))
        action = np.argmax(prediction)
        return TrainedRLPlayer._action_to_move(self, action, battle)
