import numpy as np
import tensorflow as tf
import os
import BattleUtilities

from poke_env.player.env_player import Gen8EnvSinglePlayer
from poke_env.player.random_player import RandomPlayer

from rl.agents.dqn import DQNAgent
from rl.policy import LinearAnnealedPolicy, EpsGreedyQPolicy
from rl.memory import SequentialMemory
from tensorflow.keras.layers import Dense, Flatten, Dropout
from tensorflow.keras.models import Sequential
from tensorflow.keras.optimizers import Adam
from tensorflow.keras import layers
from PlayerModels import SelfBattler2, MaxDamagePlayer, MinimaxPlayer, SmartDamagePlayer, TrainedRLPlayer

# This will disable the gpu and make the training run on cpu
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
# We define our RL player
# It needs a state embedder and a reward computer, hence these two methods
class SelfBattler1(Gen8EnvSinglePlayer):
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
        #matchup_score = self.get_matchup_score(battle.active_pokemon, battle.opponent_active_pokemon)
        # Final vector with 11 components
        return np.concatenate(
            [
                moves_base_power,
                moves_dmg_multiplier,
                [remaining_mon_team, remaining_mon_opponent], score,
            ]
        )

    def compute_reward(self, battle) -> float:
        return self.reward_computing_helper(
            battle, fainted_value=1, hp_value=1, victory_value=9
        )



NB_TRAINING_STEPS = 10000
NB_EVALUATION_EPISODES = 100

tf.random.set_seed(0)
np.random.seed(0)


# This is the function that will be used to train the dqn
def dqn_training(player, dqn, nb_steps):
    dqn.fit(player, nb_steps=nb_steps)
    player.complete_current_battle()


def dqn_evaluation(player, dqn, nb_episodes):
    # Reset battle statistics
    player.reset_battles()
    dqn.test(player, nb_episodes=nb_episodes, visualize=True, verbose=False)

    print(
        "DQN Evaluation: %d victories out of %d episodes"
        % (player.n_won_battles, nb_episodes)
    )


if __name__ == "__main__":
    # Defining the environment  agent
    env_player = SelfBattler1(battle_format="gen8randombattle")
    # I define model here so that I can run a already trained agent for training a new agent
    model = tf.keras.models.load_model("Model_10000")

    # I define all the opponent types for training the agent
    opponent = SelfBattler2(battle_format="gen8randombattle")
    second_opponent = MaxDamagePlayer(battle_format="gen8randombattle")
    third_opponent = RandomPlayer(battle_format="gen8randombattle")
    fourth_opponent = MinimaxPlayer(battle_format="gen8randombattle")
    fifth_opponent = SmartDamagePlayer(battle_format="gen8randombattle")
    final_opponent = SelfBattler2(battle_format="gen8randombattle")
    trained_opponent = TrainedRLPlayer(model)


    # Output dimension
    #n_action = len(env_player.action_space)

    #model = Sequential()
    #model.add(Dense(128, activation="elu", input_shape=[1, 10]))

    # The embedding has shape (1, 10), which affects our hidden layer
    # dimension and output dimension
    # Flattening cause it doesn't work if I don't lol
    #model.add(Flatten())
    #model.add(Dense(64, activation="elu"))
    #model.add(Dense(n_action, activation="linear"))

    n_action = len(env_player.action_space)
    model = Sequential()
    model.add(Dense(128, activation="relu", input_shape=[1, 11]))
    model.add(Dropout(0.2))

    model.add(Dense(128, activation="relu"))
    model.add(Dropout(0.2))

    model.add(Flatten())
    model.add(Dense(64))

    model.add(Dense(n_action, activation="linear"))

    memory = SequentialMemory(limit=10000, window_length=1)

    # Ssimple epsilon greedy
    policy = LinearAnnealedPolicy(
        EpsGreedyQPolicy(),
        attr="eps",
        value_max=1.0,
        value_min=0.05,
        value_test=0,
        nb_steps=10000,
    )

    # Defining the DQN

    dqn = DQNAgent(
        model=model,
        nb_actions=len(env_player.action_space),
        policy=policy,
        memory=memory,
        nb_steps_warmup=1000,
        gamma=2,
        target_model_update=1,
        delta_clip=0.01,
        enable_double_dqn=False,
    )

    dqn.compile(Adam(lr=0.001), metrics=["mae"])

    # Training
    # This is kinda scuffed, but I can't manually change the number of training steps beyond 10000 for some reason, so I made a loop to train 10000 times each time the loops runs
    runs = 3
    for i in range(runs):
        i = i + 1
        print("{}".format(i), "/", "{}".format(runs))
        
        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )
        
        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=second_opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )
        
        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=third_opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )
        '''
        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=fourth_opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )
        
        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=fifth_opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )
        
        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=final_opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )

        env_player.play_against(
            env_algorithm=dqn_training,
            opponent=trained_opponent,
            env_algorithm_kwargs={"dqn": dqn, "nb_steps": NB_TRAINING_STEPS},
        )'''
        print("{}".format(i), "/", "{}".format(runs))
    model.save("model_%d" % NB_TRAINING_STEPS)

    # Evaluation and results (Plays against all the different opponents after training)
    print("Results against Self(1st Battle):")
    env_player.play_against(
        env_algorithm=dqn_evaluation,
        opponent=opponent,
        env_algorithm_kwargs={"dqn": dqn, "nb_episodes": NB_EVALUATION_EPISODES},
    )

    print("Results against Max Damage player:")
    env_player.play_against(
        env_algorithm=dqn_evaluation,
        opponent=second_opponent,
        env_algorithm_kwargs={"dqn": dqn, "nb_episodes": NB_EVALUATION_EPISODES},
    )

    print("Results against random player:")
    env_player.play_against(
        env_algorithm=dqn_evaluation,
        opponent=third_opponent,
        env_algorithm_kwargs={"dqn": dqn, "nb_episodes": NB_EVALUATION_EPISODES},
    )

    print("Results against Min-Max player:")
    env_player.play_against(
        env_algorithm=dqn_evaluation,
        opponent=fourth_opponent,
        env_algorithm_kwargs={"dqn": dqn, "nb_episodes": NB_EVALUATION_EPISODES},
    )

    print("Results against Smart-Damage player:")
    env_player.play_against(
        env_algorithm=dqn_evaluation,
        opponent=fifth_opponent,
        env_algorithm_kwargs={"dqn": dqn, "nb_episodes": NB_EVALUATION_EPISODES},
    )

    print("Results against Self(2nd Battle):")
    env_player.play_against(
        env_algorithm=dqn_evaluation,
        opponent=final_opponent,
        env_algorithm_kwargs={"dqn": dqn, "nb_episodes": NB_EVALUATION_EPISODES},
    )